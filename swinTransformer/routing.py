from django.urls import re_path
from swinTransformer import consumer

websocket_urlpatterns = [
    re_path(r'ws/some_path/$', consumer.TaskConsumer.as_asgi(), name='get_task_status_and_result')
]
