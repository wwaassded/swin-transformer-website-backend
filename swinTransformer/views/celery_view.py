from celery.result import AsyncResult
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


@require_http_methods(['GET'])
@csrf_exempt
def get_celery_task_status_and_result(request, task_id: int):
    pass
