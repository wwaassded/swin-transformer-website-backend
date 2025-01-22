# 基于swin-transformer的图片分割网站

## 后端部分采用django框架+mysql+redis来实现

前端部分参见 https://github.com/wwaassded/swin-transformer-website-fronend

**resently TODO**

* [x]  ~~实现历史结果界面的图片删除功能 并且 解决 删除图片时的一致性问题~~
* [x]  ~~对于用户的历史结果界面图片的缓存数量应该有一定的限制 考虑一个合适的淘汰策略~~
* [ ]  采用先更新数据库 后删除缓存的策略 但是在数据库操作成功且缓存删除错误时 仍然存在一致性问题 如何解决
* [ ]  实现历史结果界面的 图片模糊查询功能
  *...... MORE TODO*
