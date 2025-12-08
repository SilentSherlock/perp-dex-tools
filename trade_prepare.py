import os


def proxy_on():
    """
    This function is a placeholder for enabling a proxy.
    """
    # # 先清除已有的代理设置
    for key in ('HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy', 'ALL_PROXY', 'all_proxy', 'NO_PROXY', 'no_proxy'):
        os.environ.pop(key, None)
    print("Cleared proxy-related environment variables")


    # 在代码中设置全局代理
    os.environ['HTTP_PROXY'] = 'http://127.0.0.1:10809'
    os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:10809'

    # print("HTTP_PROXY and HTTPS_PROXY set to 10809 ")

    # 配置socket代理
    # os.environ['ALL_PROXY'] = 'socks5://127.0.0.1:10808'
    # os.environ['all_proxy'] = 'socks5://127.0.0.1:10808'

    # print("ALL_PROXY and all_proxy set to 10808 ")