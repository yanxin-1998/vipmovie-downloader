import requests,time,json,wx,os,glob,threading
from multiprocessing.pool import ThreadPool
from urllib3.exceptions import InsecureRequestWarning
from retrying import retry
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class NBB(threading.Thread):
    def __init__(self,url,path,frame,*args,**kwargs):
        super().__init__(*args, **kwargs)
        self.url=url
        self.path=path
        self.frame=frame

    @retry(stop_max_attempt_number=5)
    def get_url(self):
        sess = requests.session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.79 Safari/537.36'
        }
        data = {
            'movieUrl': self.url
        }
        # 通过牛巴巴借口，抓取电影资源m3u8地址
        res = sess.post('https://jx.688ing.com/parse/op/play', headers=headers, data=data, verify=False)
        # 获取标题和初步m3u8_url
        print(json.loads(res.text))
        title = json.loads(res.text)['movieInfo'][0]
        # https://cdn-yong.bejingyongjiu.com/20200822/19954_d272e2bd/index.m3u8
        m3u8_url = json.loads(res.text)['videoUrl']
        # 提取含有ts地址的m3u8_url
        # https://cdn-yong.bejingyongjiu.com/20200822/19954_d272e2bd/1000k/hls/index.m3u8
        res = sess.get(m3u8_url, headers=headers, verify=False)
        m3u8_url = m3u8_url.replace(m3u8_url.split('/')[-1], res.text.split('\n')[-1])
        res = sess.get(m3u8_url, headers=headers, verify=False,timeout=5)
        urls=[]
        for i in res.text.split(',')[1:]:
            # 构造ts_url
            ts_url = m3u8_url.replace(m3u8_url.split('/')[-1], i.split('#')[0].replace('\n', ''))
            urls.append(ts_url)
        print(urls)
        return title,urls

    #重试(非常重要，有的视频请求出现问题一直卡在那里，线程也会一直执行不完)
    @retry(stop_max_attempt_number=5) #最大重试次数5
    def demo(self,url,lock):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.79 Safari/537.36'
        }
        global count,total                                  #超过五秒没下来就报错，让其重试
        res = requests.get(url, headers=headers,verify=False,timeout=5)
        with open(self.path + '/' + url[-9:], 'wb') as f:
            f.write(res.content)
        lock.acquire()  #上锁
        count+=1
        self.frame.SetStatusText('下载进度: {}%'.format('%.2f'%(count/total*100)),1)
        lock.release()  #解锁

    def download(self,urls):
        pool = ThreadPool(50)  # 50个线程
        start = time.time()
        global count,total
        count=0
        total=len(urls)
        lock=threading.Lock()
        for url in urls:
            pool.apply_async(self.demo,(url,lock))

        pool.close()
        pool.join()
        all_time=time.time() - start
        self.frame.SetStatusText('下载完成，用时{}分{}秒'.format(int(all_time//60),int(all_time%60)), 1)

    def gen_mp4(self,title):
        # os命令合并视频，记得路径要用\,用这个/会出错
        os.system('copy /b {}\*.ts {}\{}.mp4'.format(self.path, self.path, title))
        # 删除ts片段
        tses = glob.glob('{}/*.ts'.format(self.path.replace('\\', '/')))
        for i in tses:
            os.remove(i)

    def run(self):
        try:
            title,urls=self.get_url()
            self.download(urls)
            self.gen_mp4(title)
        except Exception as e:
            self.frame.SetStatusText('下载失败', 1)
            print(e)

class WMXZ(threading.Thread):
    def __init__(self,url,path,frame,*args,**kwargs):
        super().__init__(*args, **kwargs)
        self.url=url
        self.path=path
        self.frame=frame

    def run(self):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.79 Safari/537.36'
            }
            data = {
                'movieUrl': self.url
            }
            #通过牛巴巴接口获取电影名
            res = requests.post('https://jx.688ing.com/parse/op/play', headers=headers, data=data, verify=False)
            title = json.loads(res.text)['movieInfo'][0]
            print(title)

            data={
                'url':self.url
            }
            #通过无名小站接口获取电影url
            res = requests.post('https://www.administratorm.com/WMXZ.WANG/api.php', data=data, headers=headers)
            url=json.loads(res.text)['url']
            print(json.loads(res.text))

            if url[-4:]=='.mp4':
                start = time.time()
                # 当把get函数的stream参数设置成True时，它不会立即开始下载，当你使用iter_content或iter_lines遍历内容或访问内容属性时才开始下载
                # 这个时候就能在下载前得到response.headers里的content-length了
                res=requests.get(url,headers=headers,stream=True)
                total_length=int(res.headers['Content-Length'])
                percent_length=int(total_length/200)
                download_length=0
                with open(self.path+'/'+title+'.mp4','wb')as f:
                    for chunk in res.iter_content(chunk_size=percent_length):  #分段，每段这么长
                        f.write(chunk)
                        download_length+=percent_length
                        #下载百分比
                        percent=download_length / total_length
                        if percent>1:  #最后一段
                            percent=1
                        self.frame.SetStatusText('下载进度: {}%'.format('%.2f' % (percent * 100)), 1)

                all_time = time.time() - start
                self.frame.SetStatusText('下载完成，用时{}分{}秒'.format(int(all_time // 60), int(all_time % 60)), 1)

            elif url[-5:]=='.m3u8':   #如果是m3u8文件就用牛巴巴的处理方式
                res = requests.get(url, headers=headers, verify=False)
                m3u8_url = url.replace(url.split('/')[-1], res.text.split('\n')[-1])
                res = requests.get(m3u8_url, headers=headers, verify=False, timeout=5)
                urls = []
                for i in res.text.split(',')[1:]:
                    # 构造ts_url
                    ts_url = m3u8_url.replace(m3u8_url.split('/')[-1], i.split('#')[0].replace('\n', ''))
                    urls.append(ts_url)
                print(urls)

                NBB(self.url,self.path,self.frame).download(urls)
                NBB(self.url,self.path,self.frame).gen_mp4(title)

            else:
                self.frame.SetStatusText('未知链接'.format(url), 1)

        except Exception as e:
            self.frame.SetStatusText('下载失败', 1)
            print(e)

class CreateFrame(wx.Frame):
    def __init__(self, *args, **kw):
        # ensure the parent's __init__ is called
        super(CreateFrame, self).__init__(*args, **kw)
        self.port='nbb'

        # create a panel(面板)
        self.pnl = wx.Panel(self)
        #创建文本和输入框
        self.title=wx.StaticText(self.pnl,label='请输入电影url和储存位置',pos=(150,20))
        self.label_url=wx.StaticText(self.pnl,label='电影url',pos=(50,50))      #文本左对齐
        self.text_url=wx.TextCtrl(self.pnl,pos=(100,50),size=(235,25),style=wx.TE_LEFT)
        self.label_path = wx.StaticText(self.pnl, label='储存地址', pos=(50, 90))  # 文本左对齐
        self.text_path = wx.TextCtrl(self.pnl, pos=(100, 90), size=(235, 25), style=wx.TE_LEFT)
        #按钮
        self.button_nbb=wx.Button(self.pnl,label='标清接口(默认)',pos=(100,130))
        self.button_wmxz = wx.Button(self.pnl, label='高清接口', pos=(220, 130))
        self.button_start=wx.Button(self.pnl,label='开始下载',pos=(170,180))

        self.button_nbb.Bind(wx.EVT_BUTTON,self.onclick_nbb)
        self.button_wmxz.Bind(wx.EVT_BUTTON,self.onclick_wmxz)
        self.button_start.Bind(wx.EVT_BUTTON,self.onclick_start)
        # create status bar(状态栏）
        statusBar = self.CreateStatusBar()
        statusBar.SetFieldsCount(2) #分两栏
        statusBar.SetStatusWidths([-3, -2]) #两栏宽度是3:2

    def onclick_nbb(self,event):
        self.port='nbb'

    def onclick_wmxz(self,exent):
        self.port='wmxz'

    def onclick_start(self,event):
        message = ""
        url = self.text_url.GetValue()  # 获取输入的url
        path = self.text_path.GetValue()  # 获取输入的path
        if url == "" or path == "":  # 判断url或path是否为空
            message = '电影url或储存地址不能为空'
            wx.MessageBox(message)  # 弹出提示框
        elif not os.path.exists(path):  # path不正确
            message = '储存路径有误'
            wx.MessageBox(message)  # 弹出提示框
        else:                         #第二栏显示
            self.SetStatusText('下载开始',1)
            #把耗时的部分弄成线程他就不会一直未响应，也能更新下载进度
            if self.port=='nbb':
                t= NBB(url, path, self)
                t.start()
            else:
                t=WMXZ(url, path, self)
                t.start()


if __name__ == '__main__':
    app = wx.App()
    frm = CreateFrame(None, title='焱鑫vip电影下载器', size=(400, 300))
    frm.Show()
    app.MainLoop()