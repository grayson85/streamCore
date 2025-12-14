# StreamCore 分类映射增强功能说明

## 问题
在配置分类映射时，用户不知道远程资源站有哪些分类 ID，导致无法正确配置映射关系。

## 解决方案

已增强 `setup.py` 中的 `map-type` 命令，现在会：

### 1. 自动获取远程分类（MacCMS V10 标准）

**正确方法**：从 API 响应的 **`class`** 字段获取分类列表

```python
def fetch_remote_types(source):
    """从资源站 API 获取远程分类列表"""
    # 请求: /api.php/provide/vod/?ac=list
    data = response.json()
    
    # MacCMS V10 标准：从 class 字段获取完整分类列表
    class_list = data.get('class', [])
    # class: [
    #   {"type_id": 1, "type_name": "电影"},
    #   {"type_id": 2, "type_name": "连续剧"},
    #   ...
    # ]
    
    for cls in class_list:
        type_id = str(cls.get('type_id'))
        type_name = cls.get('type_name')
```

**备用方案**：如果 API 不返回 `class` 字段，则从影片列表中提取

### 2. 显示远程和本地分类
同时显示远程和本地的分类列表，方便对照配置：
```
📡 远程分类列表：
   [1] 电影
   [2] 连续剧
   [3] 综艺
   [4] 动漫

📂 本地分类列表：
   [1] 电影
   [2] 电视剧
   [3] 动漫
   [4] 综艺
   [5] 纪录片
```

### 3. 智能推荐映射
基于分类名称自动推荐映射关系：
```
💡 建议的映射（基于远程分类名称）：
   1:1  # 电影 → 电影
   2:2  # 连续剧 → 电视剧
   3:4  # 综艺 → 综艺
   4:3  # 动漫 → 动漫
```

用户可以直接复制这些推荐的映射配置，或根据需要调整。

## 使用示例

### 完整流程

```bash
# 1. 添加资源站
$ python3 setup.py add-source
资源站名称: CK资源网
API URL: https://ckzy.me/api.php/provide/vod/
数据格式: json
ID 前缀: ckzy

# 2. 配置分类映射（现在会自动显示远程分类）
$ python3 setup.py map-type --source ckzy

============================================================
🗺️  配置分类映射
============================================================

📌 资源站：CK资源网 (ckzy)
🌐 API URL: https://ckzy.me/api.php/provide/vod/

🌐 正在从资源站获取分类列表...
   请求: https://ckzy.me/api.php/provide/vod/?ac=list&pg=1
   ✅ 成功获取 8 个分类

📡 远程分类列表：
   [1] 电影
   [2] 连续剧
   [3] 综艺
   [4] 动漫
   [6] 动作片
   [7] 喜剧片
   [20] 大陆剧
   [21] 港台剧

📂 本地分类列表：
   [1] 电影
   [2] 电视剧
   [3] 动漫
   [4] 综艺
   [5] 纪录片

💡 建议的映射（基于远程分类名称）：
   1:1  # 电影 → 电影
   2:2  # 连续剧 → 电视剧
   3:4  # 综艺 → 综艺
   4:3  # 动漫 → 动漫
   6:1  # 动作片 → 电影
   7:1  # 喜剧片 → 电影
   20:2  # 大陆剧 → 电视剧
   21:2  # 港台剧 → 电视剧
============================================================

🔗 映射规则 (或输入 q 完成): 1:1
   ✅ 远程 1 → 本地 1 (电影)
🔗 映射规则 (或输入 q 完成): 2:2
   ✅ 远程 2 → 本地 2 (电视剧)
🔗 映射规则 (或输入 q 完成): q

============================================================
✅ 分类映射已保存！共 2 条映射规则
============================================================
```

## 兼容性

### 成功获取分类的情况
资源站返回标准 MacCMS 格式，包含 `type_id` 和 `type_name` 字段

### 无法获取分类的情况
如果网络失败或资源站格式不标准，会显示提示：
```
⚠️  无法自动获取远程分类，您需要查看资源站文档或手动测试
   您也可以先采集一次数据，然后查看数据库中的分类信息
```

此时可以：
1. 查看资源站的 API 文档
2. 先执行一次 `collector.py` 采集，然后查询数据库：
   ```bash
   sqlite3 sc_main.db "SELECT DISTINCT vod_type_id FROM sc_vod;"
   ```
3. 手动输入映射关系

## 技术细节

### MacCMS V10 标准分类获取

从 API 响应的 `class` 字段获取完整分类列表：

```python
# MacCMS V10 API 响应结构
{
  "code": 1,
  "msg": "数据列表",
  "class": [              # ← 完整的分类列表
    {"type_id": 1, "type_name": "电影"},
    {"type_id": 2, "type_name": "连续剧"},
    {"type_id": 3, "type_name": "综艺"},
    {"type_id": 4, "type_name": "动漫"}
  ],
  "list": [...],          # 影片列表
  "page": 1,
  "pagecount": 100
}

# 解析逻辑
class_list = data.get('class', [])
for cls in class_list:
    type_id = str(cls.get('type_id'))
    type_name = cls.get('type_name')
    type_dict[type_id] = type_name
```

### 备用方案

如果 API 不返回 `class` 字段（非标准实现），则从影片列表提取：

```python
# 从影片列表中提取分类
vod_list = data.get('list', [])
for vod in vod_list:
    type_id = str(vod.get('type_id', ''))
    type_name = vod.get('type_name', f'分类{type_id}')
    if type_id and type_id not in type_dict:
        type_dict[type_id] = type_name
```

### 智能映射推荐
基于关键词匹配：
```python
if '电影' in remote_name or 'movie' in remote_lower:
    suggested_local = 1  # 电影
elif '电视' in remote_name or '剧' in remote_name:
    suggested_local = 2  # 电视剧
elif '动漫' in remote_name or 'anime' in remote_lower:
    suggested_local = 3  # 动漫
# ...
```

## 总结

增强后的 `map-type` 命令大大简化了分类映射的配置流程：
- ✅ 自动获取远程分类列表
- ✅ 智能推荐映射关系
- ✅ 清晰的提示和引导
- ✅ 兼容各种情况（成功/失败）

用户只需要根据显示的分类列表和推荐配置，复制粘贴即可快速完成映射配置。
