from django.urls import path

from . import views

app_name = 'swinTransformer'

urlpatterns = [
    path('login/', views.login, name='login'),  # 用户的登录
    path('logout/', views.logout, name='logout'),  # 用户的注销
    path('logup/', views.logup, name='logup'),  # 用户的注册
    path('upload/', views.upload_file, name='upload'),  # 对用户提交的照片进行处理
    path('delete/', views.deleteImage, name='delete_image'),  # 删除指定id的图片对
    path('download/<str:filename>/', views.download_image, name='download_image'),  # 下载指定的分割图片
    path('getImage/<int:page_number>/<int:lines_per_page>', views.get_images_by_page, name='get_images_by_page'),
    # 返回图片信息 并提供后端分页功能
    path('getPageNumber/', views.get_max_page_number, name='get_page_number'),  # 获取该用户的全部页数
    path('verify/<str:verification_token>', views.verify_user_emil, name='verify_user_email'),  # 用于验证用户的邮箱是否属于该用户
]
