import os
from mootdx.reader import Reader

TDX_DIR = r"C:\new_haitong"

print("=" * 50)
print("1. 检查 vipdoc 目录结构")
print("=" * 50)

vipdoc = os.path.join(TDX_DIR, "vipdoc")
if os.path.exists(vipdoc):
    print(f"vipdoc 存在：{vipdoc}")
    print("子文件夹：")
    for item in os.listdir(vipdoc):
        sub = os.path.join(vipdoc, item)
        if os.path.isdir(sub):
            print(f"  - {item}")
            # 看看里面有什么
            for sub2 in os.listdir(sub)[:5]:
                print(f"      {sub2}")
else:
    print(f"vipdoc 不存在：{vipdoc}")
    print("可能通达信数据目录不在这里，检查一下。")

print()
print("=" * 50)
print("2. 检查 lday 目录（日线数据）")
print("=" * 50)

for market in ["sh", "sz", "bj"]:
    lday = os.path.join(vipdoc, market, "lday")
    if os.path.exists(lday):
        files = os.listdir(lday)
        print(f"{market}/lday：{len(files)} 个文件")
        if files:
            print(f"  示例：{files[:3]}")
    else:
        print(f"{market}/lday：不存在")

print()
print("=" * 50)
print("3. 测试 reader.block 返回结构")
print("=" * 50)

reader = Reader.factory(market='std', tdxdir=TDX_DIR)

block_file = os.path.join(TDX_DIR, "T0002", "hq_cache", "block_gn.dat")
print(f"板块文件：{block_file}")
print(f"文件存在：{os.path.exists(block_file)}")

try:
    df = reader.block(symbol=block_file, group=True)
    print(f"\n返回类型：{type(df)}")
    if df is not None:
        print(f"数据形状：{df.shape}")
        print(f"列名：{list(df.columns)}")
        print(f"\n前 5 行：")
        print(df.head())
except Exception as e:
    print(f"读取失败：{type(e).__name__}: {e}")

    # 试试 group=False
    print("\n试试 group=False：")
    try:
        df = reader.block(symbol=block_file, group=False)
        print(f"返回类型：{type(df)}")
        if df is not None:
            print(f"数据形状：{df.shape}")
            print(f"列名：{list(df.columns)}")
            print(df.head())
    except Exception as e2:
        print(f"也失败：{type(e2).__name__}: {e2}")