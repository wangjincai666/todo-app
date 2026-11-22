# 待办清单（Web + AI）

一个待办清单网页：能增删改查，数据存在服务器上，并接入了大模型。
除了聊天，AI 还能通过工具调用**直接操作数据库**——说一句“帮我加一条明天交实验报告”，数据库里真的会多一条。

## 技术栈

| 层 | 选择 |
| --- | --- |
| 前端 | 原生 HTML / CSS / JavaScript |
| 后端 | Python 3 + Flask |
| 数据库 | SQLite（Python 内置 sqlite3） |
| 模型 | 智谱 GLM-4-Flash（OpenAI 兼容接口） |
| 部署 | 前端 GitHub Pages / 后端 Render |

## 本地运行

1. 安装依赖

   ```bash
   python -m pip install -r requirements.txt