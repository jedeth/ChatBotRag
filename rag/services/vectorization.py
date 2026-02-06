"""
Service de vectorisation de documents.

Responsabilités :
  - Extraction du texte brut (PDF, DOCX, XLSX, TXT, MD)
  - Découpage en chunks avec chevauchement

Le stockage des embeddings en pgvector est géré par la tâche Celery
(rag/tasks.py) qui appelle albert_client puis fait un bulk_create
sur DocumentChunk.

Porté depuis chatbot/services/vectorization.py — la partie ChromaDB
a été retirée (remplacée par l'ORM Django + pgvector).
"""
import os
import logging
from typing import List, Dict

import fitz  # PyMuPDF
from docx import Document as DocxDocument
import openpyxl
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger('rag')


class VectorizationService:
    """Extraction et découpage de texte depuis des documents uploadés."""

    def __init__(self):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        # Métadonnées extraites lors de l'extraction (pour stocker dans Document.metadata)
        self.extracted_metadata = {}

    # ------------------------------------------------------------------
    # Extraction de texte selon le format
    # ------------------------------------------------------------------

    def extract_text(self, file_path: str, filename: str) -> str:
        """
        Extrait le texte brut d'un fichier selon son extension.

        Formats supportés : .pdf .docx .xlsx .txt .md

        Note: Les métadonnées extraites (stats XLSX, nombre de pages PDF, etc.)
        sont stockées dans self.extracted_metadata pour être sauvegardées
        dans Document.metadata par la tâche Celery.
        """
        ext = os.path.splitext(filename)[1].lower()

        # Réinitialiser les métadonnées pour chaque extraction
        self.extracted_metadata = {'format': ext[1:]}  # 'pdf', 'xlsx', etc.

        extractors = {
            '.pdf':  self._extract_pdf,
            '.docx': self._extract_docx,
            '.xlsx': self._extract_xlsx,
            '.txt':  self._extract_text,
            '.md':   self._extract_text,
        }

        extractor = extractors.get(ext)
        if not extractor:
            raise ValueError(f"Format non supporté : {ext}")

        try:
            text = extractor(file_path)
            logger.info(f"Texte extrait de {filename} : {len(text)} caractères")
            return text
        except Exception as e:
            logger.error(f"Erreur extraction {filename} : {e}")
            raise

    def _extract_pdf(self, file_path: str) -> str:
        """PDF → texte avec numéros de page (PyMuPDF)."""
        doc = fitz.open(file_path)
        pages = []
        for page_num, page in enumerate(doc, start=1):
            pages.append(f"\n\n--- Page {page_num} ---\n\n{page.get_text()}")

        # Stocker les métadonnées PDF
        self.extracted_metadata.update({
            'page_count': len(doc),
            'has_toc': len(doc.get_toc()) > 0
        })
        logger.info(f"PDF metadata: {len(doc)} page(s)")

        doc.close()
        return "".join(pages)

    def _extract_docx(self, file_path: str) -> str:
        """DOCX → texte paragraphe par paragraphe."""
        doc = DocxDocument(file_path)
        return "\n\n".join(para.text for para in doc.paragraphs)

    def _extract_xlsx(self, file_path: str) -> str:
        """XLSX → texte avec noms de feuilles et métadonnées statistiques."""
        wb = openpyxl.load_workbook(file_path)
        sheets = []

        # Métadonnées globales du fichier
        xlsx_metadata = {
            'sheets': [],
            'total_data_rows': 0,
            'total_rows': 0
        }

        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            rows = []

            # Extraire toutes les lignes
            all_rows = list(sheet.iter_rows(values_only=True))

            # Générer les métadonnées statistiques
            total_rows = len(all_rows)
            data_rows = total_rows - 1 if total_rows > 0 else 0  # Sans l'en-tête

            # Stocker les métadonnées de cette feuille
            sheet_metadata = {
                'name': sheet_name,
                'total_rows': total_rows,
                'data_rows': data_rows,
                'columns': []
            }

            # En-tête de feuille avec statistiques
            header = f"\n\n--- Feuille : {sheet_name} ---\n"
            header += f"STATISTIQUES : {data_rows} lignes de données, {total_rows} lignes au total"

            # Si on a un en-tête, l'afficher
            if all_rows and len(all_rows) > 0:
                first_row = all_rows[0]
                columns = [str(c) for c in first_row if c is not None]
                if columns:
                    sheet_metadata['columns'] = columns
                    header += f", {len(columns)} colonnes\n"
                    header += f"COLONNES : {' | '.join(columns)}\n"

            header += "\n"

            # Convertir toutes les lignes en texte
            for row in all_rows:
                rows.append(" | ".join(str(c) for c in row if c is not None))

            sheets.append(header + "\n".join(rows))

            # Accumuler les statistiques globales
            xlsx_metadata['sheets'].append(sheet_metadata)
            xlsx_metadata['total_data_rows'] += data_rows
            xlsx_metadata['total_rows'] += total_rows

        # Stocker les métadonnées pour utilisation dans tasks.py
        self.extracted_metadata.update(xlsx_metadata)
        logger.info(
            f"XLSX metadata: {len(xlsx_metadata['sheets'])} feuille(s), "
            f"{xlsx_metadata['total_data_rows']} lignes de données"
        )

        return "".join(sheets)

    def _extract_text(self, file_path: str) -> str:
        """TXT / MD → lecture brute UTF-8."""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    # ------------------------------------------------------------------
    # Découpage en chunks
    # ------------------------------------------------------------------

    def chunk_text(self, text: str, filename: str, min_chunk_size: int = 50) -> List[Dict]:
        """
        Découpe un texte en chunks avec métadonnées complètes.

        Filtre les chunks trop courts (pages vides, headers seuls, etc.)
        pour éviter de polluer la base vectorielle.

        Args:
            text: Texte à découper
            filename: Nom du fichier source (pour traçabilité)
            min_chunk_size: Taille minimale d'un chunk (défaut: 50 caractères)

        Returns:
            [
                {
                    "content": "texte du chunk",
                    "metadata": {
                        "source": "filename.pdf",
                        "chunk_index": 0,
                        "original_index": 0,
                        "char_count": 950
                    }
                },
                ...
            ]
        """
        raw_chunks = self.text_splitter.split_text(text)

        # Filtrer les chunks trop courts en conservant les métadonnées
        filtered_chunks = []
        original_index = 0

        for chunk in raw_chunks:
            if len(chunk.strip()) >= min_chunk_size:
                filtered_chunks.append({
                    "content": chunk,
                    "metadata": {
                        "source": filename,
                        "chunk_index": len(filtered_chunks),
                        "original_index": original_index,
                        "char_count": len(chunk)
                    }
                })
            original_index += 1

        if len(filtered_chunks) < len(raw_chunks):
            logger.info(
                f"Filtré {len(raw_chunks) - len(filtered_chunks)} chunks vides "
                f"({len(filtered_chunks)} chunks conservés)"
            )

        return filtered_chunks
