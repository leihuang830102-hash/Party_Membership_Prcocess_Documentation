from app import create_app

app = create_app()

if __name__ == '__main__':
    # 开发模式下禁用静态文件缓存
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    app.run(debug=True, port=5003, host='0.0.0.0')
