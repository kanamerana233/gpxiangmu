# 使用官方Python镜像作为基础
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目所有文件到工作目录
COPY . .

# 暴露端口。Back4App会通过$PORT环境变量指定端口，这里先声明一个默认端口
EXPOSE 8501

# 启动Streamlit应用，使用$PORT环境变量
CMD streamlit run app.py --server.port=$PORT --server.address=0.0.0.0