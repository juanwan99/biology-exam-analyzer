# 双入口约定

智能审题同一套前后端，两套账单。优化时不要再长出第三套。

## IP 评审站

- 地址：http://117.72.183.223
- 判断：前端 hostname 是 IPv4
- 登录：本地 admin_users（user001-user100 等）
- Key：admin / reviewer / teacher* 用系统 Key；其余必须自填 DeepSeek + Qwen
- 不扣 momowan 积分

## 域名站

- 地址：https://momowan.xyz
- 登录：https://api.momowan.xyz/api/auth 邮箱账号
- 每次分析扣 200 积分
- 使用系统 Key

## 不要做

- 不要用第三个 hostname 再分叉认证
- 不要把 user* 账号接到积分系统
- 不要让域名站走本地 admin_users
