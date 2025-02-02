# 历史结果界面的模糊搜索

* 因为功能相近的api应该保持相似性所以 返回值应该拥有统一的规定

```json
JsonResponse: {
                "isSuccessful": 处理是否成功,
                "isCached": 是否是redis缓存中获取的数据,
                "original_id_list": 分割前图片的id数组,
                "original_images_list": 分割前的图片数组,
                "segmented_images_list": 分割后的图片数组,
                "message": 具体的描述信息,
                "isEmpty": 返回的结果是否是空值,
                "page_number": 搜索结果的总页数
            }
```
