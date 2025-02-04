import json

from swin import settings
from channels.generic.websocket import AsyncWebsocketConsumer


class TaskConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.task_id = None
        self.group_name = None

    async def connect(self):
        self.task_id = self.scope['url_route']['kwargs']['task_id']
        self.group_name = settings.CHANNELS_GROUP_NAME_FORMAT.format(task_id=self.task_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def task_update(self, event):
        message = json.loads(event['message'])
        if message['status'] == 'completed':
            await self.send(text_data=message['result'])
        else:
            await self.send(text_data={'message': 'something wrong in celery or channels'})
