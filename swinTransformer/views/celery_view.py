import json
from celery.result import AsyncResult
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


@require_http_methods(['GET'])
@csrf_exempt
def get_celery_task_status_and_result(request, task_id: str):
    result = AsyncResult(task_id)
    if result.failed():
        return JsonResponse({
            'isDone': True,
            'isSuccess': False,
            'traceBack': result.traceback
        })
    if result.successful():
        return JsonResponse({
            'isDone': True,
            'isSuccess': True,
            'result': json.loads(result.get())
        })
    else:
        return JsonResponse({
            'isDone': False,
            'isSuccess': False,
        })
