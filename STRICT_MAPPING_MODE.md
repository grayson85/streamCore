# 严格映射模式说明

## 🎯 什么是严格映射模式？

StreamCore 现在使用**严格映射模式**，确保只有正确映射的数据才会入库。

## ❌ 旧行为（已移除）

```python
# 旧代码：使用默认值
vod_type_id = mapping.get(remote_type_id, 1)  # 默认映射到 1
```

**问题：**
- 如果 `res_mapping` 为空 `{}`，所有数据都映射到分类1
- 导致 1999 条数据堆积在一个分类
- 数据分类混乱，无法精确查询

## ✅ 新行为（严格模式）

```python
# 新代码：严格映射
vod_type_id = mapping.get(remote_type_id)

if vod_type_id is None:
    print(f"⚠️  跳过无映射数据: {vod_name} (远程分类ID: {remote_type_id})")
    continue  # 跳过，不入库
```

**优势：**
- ✅ 防止脏数据
- ✅ 强制用户配置映射
- ✅ 数据分类准确
- ✅ 问题早发现

## 📋 采集流程变化

### 场景 1：未配置映射

```bash
$ python3 collector.py

📡 采集资源站: 无尽 (wj_)
   ⚠️  警告：资源站 '无尽' 没有配置分类映射！
   💡 请先使用 'python setup.py map-source-types --source wj_' 配置映射
   ⏭️  跳过此资源站的数据采集
```

**采集结果**：0 条数据

### 场景 2：部分映射

```bash
# 假设只映射了 6,7,8
res_mapping = {"6": 6, "7": 7, "8": 8}

$ python3 collector.py

📡 采集资源站: 无尽 (wj_)
   📄 采集第 1 页...
   ⚠️  跳过无映射数据: 综艺玩很大 (远程分类ID: 3)
   ⚠️  跳过无映射数据: 综艺新时代 (远程分类ID: 3)
   ⚠️  跳过无映射数据: 认识的哥哥 (远程分类ID: 3)
   ⚠️  跳过无映射数据: 国产剧示例 (远程分类ID: 13)
   ⚠️  跳过无映射数据: 动漫示例 (远程分类ID: 4)
   ℹ️  共跳过 150 条无映射数据
   ✅ 第 1 页处理完成，新增/更新 5 条数据
```

**采集结果**：只入库映射的分类（6,7,8）

### 场景 3：完整映射

```bash
# 映射了 30+ 个分类
res_mapping = {"6": 6, "7": 7, ..., "31": 32}

$ python3 collector.py

📡 采集资源站: 无尽 (wj_)
   📄 采集第 1 页...
   ✅ 第 1 页处理完成，新增/更新 20 条数据
   📄 采集第 2 页...
   ✅ 第 2 页处理完成，新增/更新 20 条数据
   ...
```

**采集结果**：所有映射的数据都正确入库

## 🛡️ 防护机制

### 1. 空映射检测

```python
if not mapping:
    print("⚠️  警告：没有配置分类映射！")
    print("💡 请先使用 'python setup.py map-source-types' 配置映射")
    return 0  # 直接返回，不采集
```

### 2. 跳过计数

```python
skip_count = 0

if vod_type_id is None:
    skip_count += 1
    if skip_count <= 5:  # 只显示前5个警告
        print(f"⚠️  跳过无映射数据: {vod_name}")
    continue

# 采集结束后
if skip_count > 0:
    print(f"ℹ️  共跳过 {skip_count} 条无映射数据")
```

### 3. 映射建议

系统会提示您配置映射：
```
💡 请先使用 'python setup.py map-source-types --source wj_' 配置映射
```

## 📊 对比效果

### 使用旧逻辑（默认值1）

```sql
SELECT vod_type_id, COUNT(*) FROM sc_vod GROUP BY vod_type_id;
```

**结果：**
```
1  | 1999  ❌ 全部堆积
23 | 1
```

### 使用新逻辑（严格模式）

```sql
SELECT vod_type_id, COUNT(*) FROM sc_vod GROUP BY vod_type_id;
```

**结果：**
```
6  | 180   ✅ 动作片
7  | 150   ✅ 喜剧片
8  | 120   ✅ 爱情片
20 | 350   ✅ 国产剧
21 | 110   ✅ 港台剧
22 | 140   ✅ 日韩剧
...
```

## 🚀 使用建议

### 步骤 1：清空错误数据

```bash
# 删除旧的错误数据（可选）
sqlite3 sc_main.db "DELETE FROM sc_vod;"
sqlite3 sc_main.db "DELETE FROM sc_search;"
sqlite3 sc_temp.db "DELETE FROM sc_vod;"
sqlite3 sc_temp.db "DELETE FROM sc_search;"
```

### 步骤 2：配置正确的映射

```bash
python3 setup.py map-source-types --source wj_
```

### 步骤 3：重新采集

```bash
python3 collector.py
```

### 步骤 4：验证结果

```bash
sqlite3 sc_main.db "
SELECT 
    t.type_name,
    COUNT(*) as cnt
FROM sc_vod v
JOIN sc_type t ON v.vod_type_id = t.type_id
GROUP BY t.type_name
ORDER BY cnt DESC;
"
```

## ⚠️ 注意事项

1. **首次采集必须配置映射**
   - 否则无法采集任何数据
   - 系统会明确提示

2. **部分映射会丢失数据**
   - 只映射的分类会入库
   - 未映射的会被跳过
   - 通过日志可以看到跳过的数据

3. **推荐完整映射**
   - 使用我提供的 30+ 条映射
   - 覆盖主要内容分类
   - 避免数据丢失

## 💡 总结

严格映射模式的核心理念：
- **宁可不采集，也不采集错**
- **强制配置，防止脏数据**
- **早发现问题，早解决**

这是一个更加健壮和可靠的设计！🎯
