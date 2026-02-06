import os
from django import forms
from django.conf import settings


# Extensions autorisées pour l'upload
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.xlsx', '.txt', '.md'}

# Magic bytes bloqués (fichiers exécutables / archives)
BLOCKED_MAGIC_BYTES = [
    b'\x7fELF',            # ELF (Linux executables)
    b'MZ',                # PE (Windows .exe / .dll)
    b'PK\x03\x04',        # ZIP
    b'\xfe\xed\xfa\xce',  # Mach-O 32-bit
    b'\xfe\xed\xfa\xcf',  # Mach-O 64-bit
    b'\xcf\xfa\xed\xfe',  # Mach-O 64-bit (reversed)
    b'#!/',               # Shell script
]


class DocumentUploadForm(forms.Form):
    """Formulaire d'upload de document pour vectorisation RAG."""

    file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.docx,.xlsx,.txt,.md',
        }),
        help_text='Formats : PDF, DOCX, XLSX, TXT, MD — max 100 Mo',
    )

    def clean_file(self):
        uploaded_file = self.cleaned_data['file']

        # --- Taille maximale ---
        max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 104857600)
        if uploaded_file.size > max_size:
            raise forms.ValidationError(
                f"Fichier trop grand ({uploaded_file.size / 1024 / 1024:.1f} Mo). "
                f"Maximum : {max_size / 1024 / 1024:.0f} Mo."
            )

        # --- Fichier vide ---
        if uploaded_file.size < 100:
            raise forms.ValidationError("Fichier vide ou trop petit.")

        # --- Extension autorisée ---
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError(
                f"Extension '{ext}' non supportée. "
                f"Utilisez : {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )

        # --- Magic bytes (bloque les exécutables) ---
        uploaded_file.seek(0)
        header = uploaded_file.read(4)
        uploaded_file.seek(0)

        # Exception : DOCX et XLSX sont des ZIP (Office Open XML), donc on autorise
        # les magic bytes ZIP uniquement pour ces extensions
        is_office_document = ext in {'.docx', '.xlsx'}

        for magic in BLOCKED_MAGIC_BYTES:
            if header[:len(magic)] == magic:
                # Autoriser ZIP pour les documents Office
                if magic == b'PK\x03\x04' and is_office_document:
                    continue
                raise forms.ValidationError(
                    "Type de fichier bloqué par politique de sécurité."
                )

        return uploaded_file
