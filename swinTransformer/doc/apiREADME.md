# API 功能手册(只对部分比较复杂的api进行解释)

### upload_file （具体的实现交由process_image处理）
    1.获取用户上传的图片 并将其交由swinTransformer模型脚本处理 获得结果图片
    2.在数据库中创建相对应的数据做好历史信息的记录
    3.将原照片以及结果照片存储在nginx服务器中 并使用url来进行照片的传递 并不直接传输照片
    4.将照片对在数据库中的id返回给前端 (前端可以通过id进行查询照片 获得url以便于在前端页面中向用户进行展示)
