# 基于swin-transformer的图片分割网站

## 后端部分采用django框架+mysql+redis来实现

前端部分参见 https://github.com/wwaassded/swin-transformer-website-frontend

**_current TODO_**

* [X]  ~~实现历史结果界面的图片删除功能 并且 解决 删除图片时的一致性问题~~
* [X]  ~~对于用户的历史结果界面图片的缓存数量应该有一定的限制 考虑一个合适的淘汰策略~~
* [ ]  采用先更新数据库 后删除缓存的策略 但是在数据库操作成功 但是缓存删除错误时 仍然存在一致性问题 如何解决
* [ ]  实现历史结果界面的 图片模糊查询功能
* [X]  ~~实现注册界面的邮箱激活 -> 可能会导致数据库中用户表修改 考虑存储用户的邮箱用以和用户之间的沟通~~
* [ ]  [是否应该给予用户选择是否被邮箱骚扰的权力](swinTransformer/doc/prevent_email.md)
* [ ]  用户的账号不应该同时被多台设备同时登陆
* [ ]  设计新的页面 用于展示用户的基础信息 一些简单的设置

1. 是否受到邮件的打扰
2. 基础信息的修改
3. 是否会支持用户的头像设置

* [ ]  🐶难道不应该有一个前端的TODO吗？
