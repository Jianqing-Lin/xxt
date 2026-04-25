import argparse


def Args() -> dict:
    parser = argparse.ArgumentParser(description='ice-study')
    parser.add_argument('-b','--beta',action='store_true', help="打开实验性(Beta)功能")
    parser.add_argument('-u','--update', action='store_true', help='检测并更新')
    parser.add_argument('-d','--debug', action='store_true', help='打开Debug模式')
    parser.add_argument('-n', '--no-logo', action='store_false', help='关闭Logo')
    parser.add_argument('-v','--version', action='store_true', help='Version')
    parser.add_argument('-s', '--speed', type=float, default=None, help='设置刷视频倍速，例如 1.0 或 2.0')
    parser.add_argument('--tiku-url', default='http://localhost:8060/adapter-service/search', help='tikuAdapter 搜题接口地址')
    parser.add_argument('--tiku-use', default='local,icodef,buguake', help='tikuAdapter 使用的题库源，例如 local,icodef,buguake')
    parser.add_argument('--tiku-token', action='append', default=[], help='追加题库 Token 查询参数，例如 icodefToken=xxx，可重复传入')
    args = parser.parse_args()
    debug = args.debug
    logo = args.no_logo
    v = args.version
    beta = args.beta
    update = args.update
    speed = args.speed
    return {
        'debug': debug,
        'logo': logo,
        'v': v,
        'beta': beta,
        'update': update,
        'speed': speed,
        'tiku_url': args.tiku_url,
        'tiku_use': args.tiku_use,
        'tiku_token': args.tiku_token,
    }
