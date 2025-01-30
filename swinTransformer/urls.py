from django.urls import path

from .views import user_view
from .views import image_view

app_name = 'swinTransformer'

urlpatterns = [
    path('login/', user_view.login, name='login'),  # 用户的登录
    path('logout/', user_view.logout, name='logout'),  # 用户的注销
    path('logup/', user_view.logup, name='logup'),  # 用户的注册
    path('upload/', image_view.upload_file, name='upload'),  # 对用户提交的照片进行处理
    path('delete/', image_view.deleteImage, name='delete_image'),  # 删除指定id的图片对
    path('download/<str:filename>/', image_view.download_image, name='download_image'),  # 下载指定的分割图片
    path('getImage/<int:page_number>/<int:lines_per_page>', image_view.get_images_by_page, name='get_images_by_page'),
    # 返回图片信息 并提供后端分页功能
    path('getPageNumber/', image_view.get_max_page_number, name='get_page_number'),  # 获取该用户的全部页数
    path('verify/<str:verification_token>', user_view.verify_user_emil, name='verify_user_email'),  # 用于验证用户的邮箱是否属于该用户
    path('searchImage', image_view.get_images_by_token_and_page, name='get_images_by_token_and_page')
    # 通过用户提供的token 以及页面数模糊获取images对 并将结果返回
]
