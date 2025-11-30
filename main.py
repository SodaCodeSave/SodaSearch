import urllib
import time
import json
import re
import os
import importlib.util
from flask import Flask, render_template, request, redirect, url_for
import requests
from lxml import etree
from urllib.parse import urlparse

app = Flask(__name__)

@app.route('/')
def index():
    global plugins_config
    plugins_config = load_plugins_config()
    return render_template('index.html', plugins_config=plugins_config)

@app.route('/plugins_settings', methods=['POST'])
def plugins_settings():
    plugins_dir = 'plugins'
    plugin_names = []
    if os.path.exists(plugins_dir):
        for filename in os.listdir(plugins_dir):
            if filename.endswith('.py') and not filename.startswith('__'):
                plugin_names.append(filename[:-3])
    
    config = {}
    for plugin_name in plugin_names:
        config[plugin_name] = request.form.get(f'plugin_{plugin_name}') == 'on'
    
    save_plugins_config(config)
    
    global plugins
    plugins = load_plugins(config)
    
    return redirect(url_for('index'))

def load_plugins_config():
    config_path = 'plugins_config.json'
    if not os.path.exists(config_path):
        default_config = {}
        plugins_dir = 'plugins'
        if os.path.exists(plugins_dir):
            for filename in os.listdir(plugins_dir):
                if filename.endswith('.py') and not filename.startswith('__'):
                    plugin_name = filename[:-3]
                    default_config[plugin_name] = True
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        return default_config
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    plugins_dir = 'plugins'
    if os.path.exists(plugins_dir):
        for filename in os.listdir(plugins_dir):
            if filename.endswith('.py') and not filename.startswith('__'):
                plugin_name = filename[:-3]
                if plugin_name not in config:
                    config[plugin_name] = True
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    
    return config

def save_plugins_config(config):
    config_path = 'plugins_config.json'
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def load_plugins(config):
    plugins = []
    plugins_dir = 'plugins'
    
    if not os.path.exists(plugins_dir):
        return plugins
    
    for filename in os.listdir(plugins_dir):
        if filename.endswith('.py') and not filename.startswith('__'):
            plugin_path = os.path.join(plugins_dir, filename)
            plugin_name = filename[:-3]
            
            if not config.get(plugin_name, True):
                print(f"插件 {plugin_name} 已禁用")
                continue
            
            try:
                spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
                plugin_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(plugin_module)
                
                if hasattr(plugin_module, 'get_results'):
                    plugins.append({
                        'name': plugin_name,
                        'module': plugin_module,
                        'get_results': plugin_module.get_results
                    })
                    print(f"加载插件成功: {plugin_name}")
                else:
                    print(f"插件 {plugin_name} 缺少必要的 get_results 函数")
            except Exception as e:
                print(f"加载插件 {plugin_name} 失败: {e}")
    
    return plugins

plugins_config = load_plugins_config()

plugins = load_plugins(plugins_config)

def offical_results(results):
    offical_results = json.loads(open('offical.json', 'r', encoding='utf-8').read())
    for r in results:
        try:
            domain = urlparse(r['link']).netloc.lower()
            for offical in offical_results:
                offical = offical.lower()
                if offical == domain:
                    r['official'] = offical_results[offical]
                    break
                if domain.endswith('.' + offical):
                    r['official'] = offical_results[offical]
                    break
        except:
            continue
    return results

@app.route('/proxy/image')
def proxy_image():
    image_url = "https:" + request.args.get('url').replace('https:', '')
    if not image_url:
        return 'Missing image URL', 400
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'referer': 'https://www.baidu.com/'
       }
        
        response = requests.get(image_url, headers=headers, stream=True)
        response.raise_for_status()
        
        content_type = response.headers.get('Content-Type', 'image/jpeg')
        
        return app.response_class(
            response.iter_content(chunk_size=8192),
            content_type=content_type,
            headers={'Cache-Control': 'public, max-age=3600'}
        )
    except Exception as e:
        print(f"图片代理失败: {e}")
        return redirect(url_for('static', filename='error.png'))

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query')
    page = int(request.args.get('page', 1))
    if query:
        import time
        current_time = int(time.time())
        
        all_results = []
        
        for plugin in plugins:
            try:
                plugin_results = plugin['get_results'](query)
                
                for result in plugin_results:
                    if all(key in result for key in ['title', 'link', 'outline', 'favicon', 'from']):
                        if 'score' not in result:
                            result['score'] = 70
                        result['plugin_file'] = plugin['name'] + '.py'
                        
                        if 'pic' in result and result['pic']:
                            from urllib.parse import quote
                            result['pic'] = f'/proxy/image?url={quote(result["pic"])}'
                        
                        all_results.append(result)
            except Exception as e:
                print(f"调用插件 {plugin['name']} 失败: {e}")
        
        all_results.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        per_page = 10
        total_results = len(all_results)
        total_pages = (total_results + per_page - 1) // per_page
        
        page = max(1, min(page, total_pages))
        
        start = (page - 1) * per_page
        end = start + per_page
        paginated_results = all_results[start:end]
    else:
        paginated_results = []
        total_pages = 0
    return render_template('search.html', query=query, results=paginated_results, page=page, total_pages=total_pages)

if __name__ == '__main__':
    app.run(debug=True)