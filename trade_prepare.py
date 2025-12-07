import os


def proxy_on():
    """
    This function is a placeholder for enabling a proxy.
    """
    # 在代码中设置全局代理
    os.environ['HTTP_PROXY'] = 'http://127.0.0.1:10809'
    os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:10809'

    # 配置socket代理
    os.environ['ALL_PROXY'] = 'socks5://127.0.0.1:10808'
    os.environ['all_proxy'] = 'socks5://127.0.0.1:10808'

    print("Proxy enabled: HTTP/HTTPS on 10809, SOCKS5 on 10808")