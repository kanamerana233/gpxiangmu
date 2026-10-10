import os

tdxdir = r"C:\new_haitong"   # 换成你的通达信路径

print("正在扫描通达信目录，查找板块文件...\n")

found = []
for root, dirs, files in os.walk(tdxdir):
    for f in files:
        if f.endswith(".dat") and ("block" in f.lower() or "gn" in f.lower() or "fg" in f.lower() or "zs" in f.lower()):
            full_path = os.path.join(root, f)
            size = os.path.getsize(full_path)
            found.append((full_path, size))

if not found:
    print("没有找到板块文件，可能路径不对，或者通达信版本不同。")
    print(f"当前扫描的路径：{tdxdir}")
else:
    print(f"找到 {len(found)} 个可能的板块文件：\n")
    for path, size in found:
        print(f"  {path}  ({size:,} 字节)")