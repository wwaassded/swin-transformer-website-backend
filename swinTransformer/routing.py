from django.urls import re_path
from swinTransformer import consumer

websocket_urlpatterns = [
    re_path('ws/taskStatus/<str:task_id>/', consumer.TaskConsumer.as_asgi(), name='get_task_status_and_result')
]
