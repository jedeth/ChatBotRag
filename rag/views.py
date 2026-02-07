import logging

import redis
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from .forms import DocumentUploadForm
from .models import Conversation, Document, Message
from .services.rag_engine import RAGEngine
from .tasks import vectorize_document_task

logger = logging.getLogger('rag')


# ==============================================================================
# Authentification
# ==============================================================================

def login_view(request):
    """Page de connexion."""
    if request.user.is_authenticated:
        return redirect('chat')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = authenticate(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            if user:
                login(request, user)
                messages.success(request, f'Bienvenue, {user.username} !')
                return redirect('chat')
    else:
        form = AuthenticationForm()

    return render(request, 'rag/login.html', {'form': form})


def register_view(request):
    """Page d'inscription."""
    if request.user.is_authenticated:
        return redirect('chat')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Compte créé avec succès !')
            return redirect('chat')
    else:
        form = UserCreationForm()

    return render(request, 'rag/register.html', {'form': form})


def logout_view(request):
    """Déconnexion — avec sortie SAML si activé."""
    if getattr(settings, 'SAML_ENABLED', False):
        logout(request)
        return redirect('https://arena.ac-paris.fr/login/ct_logout.jsp')

    logout(request)
    messages.info(request, 'Vous êtes déconnecté.')
    return redirect('login')


# ==============================================================================
# Pages principales
# ==============================================================================

@login_required
def chat_view(request):
    """
    Interface chat principale.

    Charge la liste des documents et des conversations de l'utilisateur.
    Si un paramètre ?conversation=<id> est présent, charge les messages
    de cette conversation pour les afficher.
    """
    documents = Document.objects.filter(user=request.user)
    conversations = Conversation.objects.filter(user=request.user)[:20]

    current_conversation = None
    chat_messages = []

    conversation_id = request.GET.get('conversation')
    if conversation_id:
        try:
            current_conversation = Conversation.objects.get(
                id=conversation_id, user=request.user
            )
            chat_messages = list(current_conversation.messages.all())
        except (Conversation.DoesNotExist, ValueError):
            pass

    return render(request, 'rag/chat.html', {
        'documents':          documents,
        'conversations':      conversations,
        'current_conversation': current_conversation,
        'chat_messages':      chat_messages,
    })


@login_required
def documents_view(request):
    """
    Page de gestion des documents :
      GET  — liste des documents + formulaire d'upload
      POST — traitement de l'upload, lancement de la vectorisation
    """
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.cleaned_data['file']

            # Créer l'enregistrement Document
            doc = Document.objects.create(
                user=request.user,
                filename=uploaded_file.name,
                file=uploaded_file,
                file_size=uploaded_file.size,
                status='pending',
            )

            # Lancer la tâche Celery
            task = vectorize_document_task.delay(doc.id)
            doc.celery_task_id = task.id
            doc.status = 'vectorizing'
            doc.save()

            messages.success(
                request,
                f'Document "{uploaded_file.name}" uploadé — vectorisation en cours.'
            )
            return redirect('documents')
    else:
        form = DocumentUploadForm()

    documents = Document.objects.filter(user=request.user)

    return render(request, 'rag/documents.html', {
        'form':      form,
        'documents': documents,
    })


@login_required
@require_POST
def document_delete_view(request, pk):
    """Supprime un document et ses chunks (CASCADE)."""
    doc = get_object_or_404(Document, pk=pk, user=request.user)
    filename = doc.filename
    doc.delete()
    messages.success(request, f'Document "{filename}" supprimé.')
    return redirect('documents')


# ==============================================================================
# API AJAX
# ==============================================================================

@login_required
@require_POST
def chat_send_view(request):
    """
    Endpoint AJAX : envoyer un message, obtenir une réponse RAG.

    POST body :
      message        — texte de la question
      conversation_id — ID de conversation existante (optionnel)
      skip_coaching  — True pour désactiver le Query Coach (optionnel)

    Retourne JSON :
      {
        "response": "…",
        "sources": […],
        "conversation_id": <int>,
        "coaching": {...}  (optionnel, si suggestions disponibles)
      }
    """
    message_text = request.POST.get('message', '').strip()
    conversation_id = request.POST.get('conversation_id', '').strip()
    skip_coaching = request.POST.get('skip_coaching', 'false').lower() == 'true'

    if not message_text:
        return JsonResponse({'error': 'Message vide'}, status=400)

    try:
        # Récupérer ou créer la conversation
        if conversation_id:
            try:
                conversation = Conversation.objects.get(
                    id=int(conversation_id), user=request.user
                )
            except (Conversation.DoesNotExist, ValueError):
                conversation = Conversation.objects.create(user=request.user)
        else:
            conversation = Conversation.objects.create(user=request.user)

        # Sauvegarder le message utilisateur
        Message.objects.create(
            conversation=conversation,
            role='user',
            content=message_text,
        )

        # Appeler le moteur RAG
        rag = RAGEngine()
        result = rag.generate_response(
            user=request.user,
            message=message_text,
            skip_coaching=skip_coaching,
        )

        # Sauvegarder la réponse assistant
        Message.objects.create(
            conversation=conversation,
            role='assistant',
            content=result['response'],
            sources=result['sources'],
        )

        # Titre de la conversation = premier message (raccourci)
        if not conversation.title:
            conversation.title = message_text[:100]
            conversation.save()

        # Construire la réponse JSON
        response_data = {
            'response':        result['response'],
            'sources':         result['sources'],
            'conversation_id': conversation.id,
        }

        # Ajouter les suggestions de coaching si disponibles
        if 'coaching' in result and result['coaching']:
            response_data['coaching'] = result['coaching']

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Erreur chat pour {request.user.username} : {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def upload_status_view(request, task_id):
    """
    Endpoint AJAX : statut d'une tâche de vectorisation Celery.

    Utilisé par le polling JavaScript sur la page documents.
    """
    from celery.result import AsyncResult

    result = AsyncResult(task_id)

    # result.info peut être dict, str ou None selon l'état
    info = result.info
    if isinstance(info, dict):
        progress = info.get('progress', 0)
        message  = info.get('message', '')
    elif isinstance(info, str):
        progress = 0
        message  = info
    else:
        progress = 0
        message  = ''

    return JsonResponse({
        'status':   result.state.lower(),
        'progress': progress,
        'message':  message,
    })


# ==============================================================================
# Health check
# ==============================================================================

@require_http_methods(["GET"])
def health_check(request):
    """
    Health check pour le monitoring des conteneurs.

    Vérifie : base de données PostgreSQL + Redis.
    """
    health = {'status': 'healthy', 'checks': {}}

    # --- PostgreSQL ---
    try:
        connection.ensure_connection()
        health['checks']['database'] = 'ok'
    except Exception as e:
        health['status'] = 'unhealthy'
        health['checks']['database'] = f'error: {e}'

    # --- Redis ---
    try:
        r = redis.from_url(settings.CELERY_BROKER_URL)
        r.ping()
        health['checks']['redis'] = 'ok'
    except Exception as e:
        health['status'] = 'unhealthy'
        health['checks']['redis'] = f'error: {e}'

    status_code = 200 if health['status'] == 'healthy' else 503
    return JsonResponse(health, status=status_code)
