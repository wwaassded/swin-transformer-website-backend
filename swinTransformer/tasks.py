import json
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from swinTransformer.tools.utils import process_image, inform_channels
from django.http import JsonResponse, HttpResponse, Http404
from django.db import transaction
from swinTransformer.tools.utils import process_image
from swinTransformer.tools.cache import *
from swinTransformer.models import User
from swinTransformer.models import OriginalImage
from swinTransformer.models import SegmentedImage


@shared_task(bind=True, max_retries=3)
def send_custom_email(self, subject, template_name, context, recipient_list):
    """
    :param self:
    :param subject: 邮件主题
    :param template_name: 邮件模板名称
    :param context: 邮件模板上下文
    :param recipient_list: 收件人列表
    """
    try:
        html_content = render_to_string(template_name, context)
        text_content = strip_tags(html_content)
        email = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, recipient_list)
        email.attach_alternative(html_content, 'text/html')
        email.send()
    except Exception as e:
        self.retry(exc=e, countdown=60)


@shared_task(bind=True)
def swin_transformer_process_image(task_id: str, user_id: int, source_image_url: str, original_img_name: str):
    segmented_image_url = process_image(original_img_name)
    try:
        with (transaction.atomic()):
            if segmented_image_url == '':
                inform_channels(task_id, json.dumps({
                    'isSuccessful': False,
                    'message': 'something wrong in swin Transformer model'
                }))
                return
            original_image = OriginalImage.objects.create(image_path=source_image_url,
                                                          user_id=user_id)
            if original_image is None:
                inform_channels(task_id, json.dumps({
                    'isSuccessful': False,
                    'message': 'something wrong in data base'
                }))
                return
            s = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            segmented_image = SegmentedImage.objects.create(
                user_id=user_id,
                original_image_id=original_image.id,
                image_path=segmented_image_url,
                created_at=s
            )
            if segmented_image is None:
                inform_channels(task_id, json.dumps({
                    'isSuccessful': False,
                    'message': 'something wrong in data base'
                }))
                return
            """
            这里的所影响的缓存一定是 用户的最后一页缓存 所以需要获取到最后一页缓存的 key
            如果需要清除缓存 那么用户一定经历过 get_images_by_page 函数
            可以在 该函数内部操作数据库时 额外查询 COUNT(*)  获取我们需要的数据
            并且 存储在全局的dict中 从而判断用户是否需要经理缓存逻辑
            """

            """
            如果删除缓存的操作失败 该如何处理
            考虑引入 消息队列处理 操作失败的情况
            重试多次后仍失败考虑数据库的回滚
            """
            # 缓存更新逻辑
            total_image_number = get_user_image_number(user_id)
            # actually total_page_number can never be none
            if total_image_number is not None:
                page_number = total_image_number // settings.DEFAULT_LINES_PER_PAGE
                left_image_number = total_image_number % settings.DEFAULT_LINES_PER_PAGE
                if left_image_number != 0:
                    page_number += 1
                    delete_user_page(user_id, page_number)  # 如果没有缓存 nothing would happen
                else:
                    # 当最后一页的image是满的情况下应该是不需要删除缓存的
                    pass
                total_image_number += 1
                set_user_image_number(user_id, total_image_number)
            user: User = User.objects.filter(id=user_id).first()
            if user is not None:
                subject = '欢迎使用'
                template_name = 'work_done_info.html'
                context = {'target': f'{settings.FRONTEND_ROOT}/detail', 'username': user.username, 'user_id': user.id,
                           'image': segmented_image_url}
                recipient_list = [user.email]
                send_custom_email.delay(subject, template_name, context, recipient_list)
            inform_channels(task_id, json.dumps({
                'isSuccessful': True,
                'source_image_id': original_image.id,
                'source_image_url': source_image_url,
                'segmented_image_url': segmented_image_url,
                'message': 'success',
            }))
            return
    except Exception as e:
        inform_channels(task_id, json.dumps({
            'isSuccessful': False,
            'message': e
        }))
        return
