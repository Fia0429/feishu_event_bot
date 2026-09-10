# Feishu Event Bot

向“海外运营部”发送两类飞书卡片：

- 每周一北京时间 10:30：海外商家机会 TOP10 Ver 1.0
- 每月 1 日北京时间 10:30：海外营销日历

## 首次配置

1. 打开仓库 **Settings → Secrets and variables → Actions**。
2. 新建 Repository secret，名称必须为 `FEISHU_WEBHOOK`。
3. Value 填写完整飞书机器人 Webhook。
4. 打开 **Actions**，选择任一工作流，点击 **Run workflow** 测试。

Webhook 不得写入代码、数据文件或 Actions 日志。

## 内容维护

- `data/weekly_top10.json`：已定稿的周度商家卡片数据。更新商家、分数、推荐理由和来源链接后，下次运行自动采用新内容。
- `data/marketing_calendar.json`：按月份维护全球节日、销售季、重点品类及相关商家。

当前版本负责可靠定时发送和模板化内容管理。没有搜索/大模型 API 时，周度情报仍需人工或外部流程更新到 `weekly_top10.json`；程序不会虚构实时新闻或流量数据。

## 本地预览

```bash
python bot.py weekly --preview
python bot.py monthly --preview
```

## 本地发送

```bash
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/..."
python bot.py weekly
```
