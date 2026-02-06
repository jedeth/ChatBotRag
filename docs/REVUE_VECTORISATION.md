# Revue approfondie de la vectorisation
**Date** : 06 février 2026
**Contexte** : Comparaison entre l'implémentation précédente (FastAPI + ChromaDB) et l'implémentation actuelle (Django + pgvector)

---

## 📊 Tableau comparatif

| Aspect | Ancienne version (IMPLEMENTATION_CHATBOT_RAG.md) | Version actuelle | Statut |
|--------|--------------------------------------------------|------------------|--------|
| **Framework** | FastAPI + ChromaDB | Django + pgvector | ✅ Migration réussie |
| **Extraction PDF** | PyMuPDF avec numéros de page | Identique | ✅ OK |
| **Extraction DOCX** | python-docx, paragraphes | Identique | ✅ OK |
| **Extraction XLSX** | Simple, sans statistiques | **Avec statistiques** (lignes, colonnes) | ✅ Amélioré |
| **Chunking** | 1000 chars, overlap 200 | Identique | ✅ OK |
| **Filtrage chunks vides** | ❌ Non | ✅ Oui (< 50 chars) | ✅ Amélioré |
| **Métadonnées chunks** | ✅ source, chunk_index, char_count | ❌ Seulement content | ⚠️ **Régression** |
| **Stockage métadonnées** | ChromaDB (collection.metadata) | Modèle Django (limité) | ⚠️ **Limitation** |
| **Gestion pages vides PDF** | Crée des chunks vides | Filtre automatiquement | ✅ Amélioré |

---

## 🔴 Problème principal identifié : Perte des métadonnées

### Ancienne version

```python
def chunk_text(self, text: str, filename: str) -> list[dict]:
    """Découpe le texte en chunks avec métadonnées."""
    chunks = self.text_splitter.split_text(text)

    return [
        {
            "content": chunk,
            "metadata": {
                "source": filename,        # Nom du fichier
                "chunk_index": i,          # Position dans le document
                "char_count": len(chunk)   # Taille du chunk
            }
        }
        for i, chunk in enumerate(chunks)
    ]
```

### Version actuelle

```python
def chunk_text(self, text: str, min_chunk_size: int = 50) -> List[Dict]:
    """Découpe un texte en chunks avec chevauchement."""
    raw_chunks = self.text_splitter.split_text(text)
    filtered_chunks = [
        {"content": chunk}  # ❌ Pas de métadonnées !
        for chunk in raw_chunks
        if len(chunk.strip()) >= min_chunk_size
    ]
    return filtered_chunks
```

**Impact** :
- ❌ Impossible de tracer la source exacte d'un chunk
- ❌ Pas de référence à la position dans le document
- ❌ Difficile de citer précisément (ex: "page 5, paragraphe 3")

---

## 🗄️ Modèle de données : Limitations actuelles

### Modèle DocumentChunk actuel

```python
class DocumentChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    embedding = VectorField(dimensions=1024)
```

**Champs manquants** pour une meilleure traçabilité :
- `source_filename` : Nom du fichier d'origine
- `char_count` : Longueur du chunk
- `metadata` : JSONField pour stocker des infos supplémentaires (page, feuille Excel, etc.)

---

## 🔍 Extraction XLSX : Analyse détaillée

### Ancienne version (simple)

```python
def _extract_xlsx(self, file_path: str) -> str:
    wb = openpyxl.load_workbook(file_path)
    text = ""
    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        text += f"\n\n--- Feuille: {sheet_name} ---\n\n"
        for row in sheet.iter_rows(values_only=True):
            text += " | ".join([str(cell) for cell in row if cell]) + "\n"
    return text
```

**Problèmes** :
- ❌ Pas d'info sur le nombre total de lignes
- ❌ Difficile de compter les enregistrements
- ❌ Pas de distinction en-tête / données

### Version actuelle (améliorée)

```python
def _extract_xlsx(self, file_path: str) -> str:
    wb = openpyxl.load_workbook(file_path)
    sheets = []

    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        all_rows = list(sheet.iter_rows(values_only=True))

        # Statistiques
        total_rows = len(all_rows)
        data_rows = total_rows - 1 if total_rows > 0 else 0

        header = f"\n\n--- Feuille : {sheet_name} ---\n"
        header += f"STATISTIQUES : {data_rows} lignes de données, {total_rows} lignes au total"

        # En-têtes de colonnes
        if all_rows:
            first_row = all_rows[0]
            columns = [str(c) for c in first_row if c is not None]
            if columns:
                header += f", {len(columns)} colonnes\n"
                header += f"COLONNES : {' | '.join(columns)}\n"

        # Données
        for row in all_rows:
            rows.append(" | ".join(str(c) for c in row if c is not None))

        sheets.append(header + "\n".join(rows))

    return "".join(sheets)
```

**Avantages** :
- ✅ Statistiques visibles dans le premier chunk
- ✅ Permet de répondre à "Combien d'élèves ?" sans compter
- ✅ Nom des colonnes explicite

**Mais** : Le problème persiste si le fichier est très grand (> 600 chunks) car seuls 5 chunks sont récupérés par requête RAG.

---

## 📄 Extraction PDF : Pages vides

### Test avec spe641_annexe_1063085.pdf

**Résultat** :
- 94 chunks créés au total
- 17 chunks vides (pages sans texte extractible)
- Chunks vides : [6, 11, 16, 22, 27, 33, 37, 42, 47, 52, 58, 63, 69, 74, 79, 84, 89]

**Causes possibles** :
1. Pages scannées (images) sans couche OCR
2. Pages de couverture graphiques
3. Tableaux complexes non reconnus par PyMuPDF

**Solution actuelle** :
```python
# Filtrage automatique des chunks < 50 caractères
filtered_chunks = [
    {"content": chunk}
    for chunk in raw_chunks
    if len(chunk.strip()) >= min_chunk_size  # Défaut: 50
]
```

✅ **Efficace** : Réduit de 94 à 77 chunks utiles pour le PDF de test.

---

## 🎯 Recommandations d'amélioration

### 1. Restaurer les métadonnées dans chunk_text ⭐ **PRIORITÉ HAUTE**

```python
def chunk_text(self, text: str, filename: str, min_chunk_size: int = 50) -> List[Dict]:
    """Découpe un texte en chunks avec métadonnées complètes."""
    raw_chunks = self.text_splitter.split_text(text)

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
                    "char_count": len(chunk),
                    "is_filtered": False
                }
            })
        original_index += 1

    if len(filtered_chunks) < len(raw_chunks):
        logger.info(
            f"Filtré {len(raw_chunks) - len(filtered_chunks)} chunks vides "
            f"({len(filtered_chunks)} chunks conservés)"
        )

    return filtered_chunks
```

**Avantages** :
- ✅ Traçabilité complète de chaque chunk
- ✅ Distinction entre index filtré et index original
- ✅ Prépare l'ajout futur de métadonnées supplémentaires

### 2. Enrichir le modèle DocumentChunk (Optionnel)

```python
class DocumentChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='chunks')
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    embedding = VectorField(dimensions=settings.EMBEDDING_DIMENSIONS)

    # Nouveaux champs
    char_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict)  # Pour infos supplémentaires (page, feuille, etc.)

    class Meta:
        ordering = ['chunk_index']
        unique_together = [('document', 'chunk_index')]
```

**Note** : Nécessite une migration. À faire uniquement si besoin réel.

### 3. Extraction PDF avancée avec OCR (Futur)

Pour les pages scannées, ajouter Tesseract OCR :

```python
def _extract_pdf_with_ocr(self, file_path: str) -> str:
    """Extrait texte d'un PDF avec fallback OCR pour images."""
    import pytesseract
    from PIL import Image

    doc = fitz.open(file_path)
    pages = []

    for page_num, page in enumerate(doc, start=1):
        text = page.get_text()

        # Si page vide, tenter OCR
        if len(text.strip()) < 20:
            pix = page.get_pixmap()
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img, lang='fra')

        pages.append(f"\n\n--- Page {page_num} ---\n\n{text}")

    doc.close()
    return "".join(pages)
```

⚠️ **Attention** : OCR est lent et consommateur de ressources. À activer seulement si besoin.

### 4. Améliorer le RAG pour les grandes tables (XLSX)

**Problème** : 796 élèves = 607 chunks, mais TOP_K = 5 → contexte insuffisant.

**Solutions possibles** :

**A. Augmenter TOP_K dynamiquement**
```python
# Dans rag_engine.py
TOP_K = 5  # Par défaut
TOP_K_LARGE_DOCS = 15  # Pour documents volumineux

def _retrieve_context(self, user: User, query: str) -> List[Dict]:
    # Détecter si la requête concerne un comptage/agrégation
    is_counting_query = any(word in query.lower() for word in
        ['combien', 'nombre', 'total', 'count', 'sum'])

    top_k = TOP_K_LARGE_DOCS if is_counting_query else TOP_K

    chunks_qs = (
        DocumentChunk.objects
        .select_related('document')
        .filter(document__user=user)
        .annotate(distance=CosineDistance('embedding', query_embedding))
        .filter(distance__lte=SIMILARITY_THRESHOLD)
        .order_by('distance')
        [:top_k]
    )
    # ...
```

**B. Ajouter un résumé au début du document**
- Déjà fait avec les statistiques XLSX ✅
- Permet de répondre aux questions de comptage sans charger tout le document

**C. Index séparé pour métadonnées structurées** (avancé)
- Stocker les statistiques dans un champ JSON du modèle Document
- Le RAG consulte d'abord les métadonnées avant de chercher dans les chunks

---

## ✅ Plan d'action proposé

### Phase 1 : Corrections immédiates (30 min)

1. ✅ Restaurer les métadonnées dans `chunk_text()` avec `filename` en paramètre
2. ✅ Mettre à jour `tasks.py` pour passer `document.filename` à `chunk_text()`
3. ✅ Tester avec un document PDF et un XLSX

### Phase 2 : Tests de régression (15 min)

1. Re-uploader les documents de test
2. Vérifier que les chunks sont bien créés
3. Vérifier que les questions RAG fonctionnent

### Phase 3 : Documentation (10 min)

1. Mettre à jour `memoire05_02_26.md` avec les changements
2. Documenter les métadonnées disponibles

**Temps total estimé** : 55 minutes

---

## 🔜 Prochaines étapes (après SAML)

1. **Migration du modèle** : Ajouter `char_count` et `metadata` à DocumentChunk
2. **OCR optionnel** : Pour les PDF scannés
3. **Optimisation TOP_K** : Ajustement dynamique selon le type de requête
4. **Statistiques avancées** : Dashboard admin pour surveiller la qualité des chunks

---

## 📝 Notes de migration ChromaDB → pgvector

**Avantages de pgvector** :
- ✅ Tout dans PostgreSQL (pas de service séparé)
- ✅ Transactions ACID
- ✅ Backup simplifié
- ✅ Index HNSW performant

**Inconvénients** :
- ❌ Pas de stockage natif des métadonnées riches (contrairement à ChromaDB)
- ❌ Nécessite d'enrichir le modèle Django pour compenser
- ❌ Moins flexible pour des recherches hybrides (texte + vecteur + metadata)

**Conclusion** : La migration est globalement réussie, mais nécessite quelques ajustements pour restaurer la richesse des métadonnées de l'ancienne version.
