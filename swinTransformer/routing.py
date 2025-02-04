from django.urls import path
from swinTransformer import consumer

websocket_urlpatterns = [
    path('ws/taskStatus/<str:task_id>/', consumer.TaskConsumer.as_asgi(), name='get_task_status_and_result')
]
