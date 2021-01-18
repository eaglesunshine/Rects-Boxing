# -*- coding: utf-8 -*-

import sys, threading, os
import time
from PIL import ImageGrab
import os
import copy
from PyQt5 import QtWidgets, QtGui, QtCore
from ui.suu import *
from itertools import combinations
from boxing import boxing


# 计算模块
calculator = boxing.Calculator()
calculator.setDaemon(True)


class MyWindow(QtWidgets.QMainWindow, threading.Thread, Ui_MainWindow):

    def __init__(self):
        super(MyWindow, self).__init__()
        self.qp = QtGui.QPainter()  # 画布
        self.readurl = ''
        self.loadurl = ''
        self.timeInterval = 0.1   # 画布刷新间隔：1为1s/0.001为 1ms
        self.now = time.time()
        self.startTime = time.time()   # 记录开始的时间戳
        self.pauseTime = 0
        self.runningTime = 0
        self.co_rect = QtCore.Qt.yellow
        self.co_tri = QtCore.Qt.green
        self.co_alarmLine = QtCore.Qt.red
        self.co_fullLine = QtCore.Qt.lightGray
        self.co_border = QtCore.Qt.darkBlue
        self.origin = (550, 120)   # 画布原点
        self.l = 30.0 # 绘图区域长
        self.h = 40.0 # 绘图区域高
        self.scale = 10  # 缩放比例
        self.iptpoints = []  # 读取的数据点: [[num, gender, [[0, 0], [0, 0], [0, 0], [0, 0]]], ...]
        self.optpoints = [[0, 0, -1, [[0,0], [0,0], [0,0]]]]  # 输出的数据点: [[s, num, gender, [[], [], [], []]], ..]
        self.fullLine = 0  # 100利用率线

        # add
        self.data = {}      # 矩形元素：{'A':[1.0, 2.0, ...], ...}
        self.select = {}    # 选择的元素：{'A':[1, 3,...],...}
        self.keyMap = {}    # num对应的字符串标识
        self.boxStr = ""
        self.possible_rects = []
        self.best_rects = []
        self.path = ""

        self.setupUi(self)
        self.buttonEvent()

        self.__flag = threading.Event()  # 用于暂停线程的标识
        self.__flag.set()  # 设置为True
        self.__running = threading.Event()  # 用于停止线程的标识
        self.__running.set()  # 将running设置为True
        self.__globalFlag = threading.Event()
        self.__globalFlag.clear()
        self.t1 = threading.Thread(target=self.refreshData)
        self.t1.start()
        calculator.start()

    # # 捕捉键盘
    # def keyPressEvent(self, a0: QtGui.QKeyEvent):
    #     # Esc
    #     if a0.key() == QtCore.Qt.Key_Escape:
    #         self.close()
    #     # S/P
    #     if a0.key() == QtCore.Qt.Key_P or a0.key() == QtCore.Qt.Key_S:
    #         self.pushButton.click()
    #
    # # 捕捉鼠标
    # def mouseMoveEvent(self, a0: QtGui.QMouseEvent):
    #     x = a0.x()
    #     y = a0.y()
    #     l = self.l*self.scale
    #     h = self.h*self.scale
    #     x0 = self.origin[0]
    #     y0 = self.origin[1]
    #
    #     if x0-5 < x < x0+l+5 and y0-5 < y < y0+h+5:
    #         x = (x-x0)/self.scale
    #         y = (y0+h-y)/self.scale
    #         text = 'x: {0}, y: {1}'.format(x, y)
    #     else:
    #         text = '请点击矩形框内以获取坐标'
    #     self.label_3.setText(text)

    # def closeEvent(self, event):
    #     '''
    #     重写主窗口退出事件，使退出的时候关闭主线程,即t2
    #     :param event:
    #     :return:
    #     '''
    #     os._exit(0)

    # 绘图事件
    def paintEvent(self, a0: QtGui.QPaintEvent):
        self.qp.begin(self)

        # 画边界框
        co1 = QtGui.QColor(QtCore.Qt.black)
        self.qp.setPen(co1)     # 设置画笔颜色
        x = self.origin[0]
        y = self.origin[1]
        # drawRect()有四个参数，分别是矩形的x、y、w、h，分别是左上角点，矩形宽度和高度
        self.qp.drawRect(x, y, self.l * self.scale, self.h * self.scale)
        # 画饱和线
        co2 = QtGui.QColor(self.co_fullLine)
        self.qp.setPen(co2)
        # self.qp.drawLine(self.origin[0],
        #                  self.origin[1] + self.scale*(self.h - self.fullLine),
        #                  self.origin[0] + self.l*self.scale,
        #                  self.origin[1] + self.scale*(self.h - self.fullLine))
        # # 显示高度
        # self.qp.drawText(self.origin[0] + self.l*self.scale + 7,
        #                  self.origin[1] + self.scale * (self.h - self.fullLine),
        #                  str(self.fullLine))

        # 画出图形
        try:
            for point in self.optpoints:    # point: [[s, num, gender, [[], [], [], []]], ..]
                num = point[1]
                gender = point[2]
                location = point[3]
                self.drawAShape(num, gender, location)
        except Exception as e:
            print(e, e)

        self.qp.end()

    def drawAShape(self, num, shape, location, scale=None):
        if not scale:
            scale = self.scale
        X = self.origin[0]  # 绘图原点X
        Y = self.origin[1] + self.scale * self.h  # 绘图原点Y

        if shape == 0:  # 0:矩形 1:三角形
            co0 = QtGui.QColor(self.co_border)
            co00 = QtGui.QColor(self.co_rect)
            self.qp.setPen(co0)
            self.qp.setBrush(co00)
            points = [int(location[0][0] * scale + X), int(-location[0][1] * scale + Y),
                      int(location[1][0] * scale + X), int(-location[1][1] * scale + Y),
                      int(location[2][0] * scale + X), int(-location[2][1] * scale + Y),
                      int(location[3][0] * scale + X), int(-location[3][1] * scale + Y),]
            polygon = QtGui.QPolygon(points)
            self.qp.drawPolygon(polygon)

            x = int((location[0][0] * scale + location[1][0] * scale ) / 2 + X)  # 标号的位置
            y = int(-(location[0][1] * scale + location[2][1] * scale) / 2 + Y)
            self.qp.drawText(x, y, self.keyMap[int(num)])

        # elif shape == 1:
        #     co1 = QtGui.QColor(self.co_border)
        #     co11 = QtGui.QColor(self.co_tri)
        #     self.qp.setPen(co1)
        #     self.qp.setBrush(co11)
        #     points = [location[0][0] * scale + X, -location[0][1] * scale + Y,
        #               location[1][0] * scale + X, -location[1][1] * scale + Y,
        #               location[2][0] * scale + X, -location[2][1] * scale + Y]
        #     polygon = QtGui.QPolygon(points)
        #     self.qp.drawPolygon(polygon)
        #
        #     x = (location[0][0]+ location[1][0] + location[2][0]-3) * scale / 3 + X  # 标号的位置
        #     y = -(location[0][1] + location[1][1] + location[2][1]-3) * scale / 3 + Y
        #     self.qp.drawText(x, y, str(num))
        else:
            return

        # 刷新利用率
        usage, y_max, remain_area = self.get_usage()
        self.label.setText('利用率：' + str(usage) + '%')

        # 刷新剩余面积
        self.label_2.setText("剩余面积: " + str(remain_area))

        # # 显示警戒线
        # co2 = QtGui.QColor(self.co_alarmLine)
        # self.qp.setPen(co2)
        # self.qp.drawLine(self.origin[0],
        #                  Y - y_max*scale,
        #                  self.origin[0] + self.l*self.scale,
        #                  Y - y_max*scale)
        # # 显示高度
        # self.qp.drawText(self.origin[0] + self.l*self.scale + 7,
        #                  self.origin[1] + (self.h-y_max)*self.scale,
        #                  str(y_max))

    def get_usage(self):
        S = 0   # 已画图形的面积
        y_arr = []
        for graph in self.optpoints:    # [[s, num, gender, [[], [], [], []]], ..]
            point = graph[3]
            S = S + graph[0]
            y_arr.extend([i[1] for i in point])

        y_max = max(y_arr)
        usage = round(S / (self.l * self.h)*100, 2) # 利用率
        remain_area = round(S, 2)

        return usage, y_max, remain_area

    # 按钮触发
    def buttonEvent(self):
        self.toolButton.clicked.connect(self.loadData)
        self.toolButton_1.clicked.connect(self.saveData)
        self.pushButton_3.clicked.connect(self.run_)
        self.pushButton_1.clicked.connect(self.confirmLoad)
        self.pushButton_2.clicked.connect(self.confirmSave)
        self.pushButton.clicked.connect(self.control)
        self.pushButton_4.clicked.connect(self.clear)

    # 读取数据
    def loadData(self):
        print('loadData...')
        self.readurl, _ = QtWidgets.QFileDialog.getOpenFileName(self, caption='选取读取路径', directory='../',
                                                             filter='*.csv')
        print(self.readurl)
        self.lineEdit.setText(self.readurl)
        self.statusBar.showMessage('    状态：选择读取路径中...')

    def getArea(self, path):
        area = 0.0
        for v in path:
            area += v[0]
        return area

    def dfs(self, rects_all, S, n, idx, path, path_all):
        if idx == n:
            return

        for i in range(len(rects_all[idx])):
            path.append(rects_all[idx][i])
            if idx == n - 1:
                area = self.getArea(path)
                if area > S:
                    path.pop()
                    continue
                path_all.append([area, copy.deepcopy(path)])
            self.dfs(rects_all, S, n, idx + 1, path, path_all)
            path.pop()

    def dfs2(self, rects_all, S, n, idx, path, path_all, limit_key, limit_value):
        if idx == n:
            return

        slections = rects_all[idx]
        if idx == limit_key:
            slections = list(combinations(rects_all[idx], limit_value))

        for i in range(len(slections)):
            if type(slections[i]) == type((1, 2)):
                path.extend(list(slections[i]))
            else:
                path.append(slections[i])
            if idx == n - 1:
                area = self.getArea(path)
                if area > S:
                    if type(slections[i]) == type((1, 2)):
                        for i in range(len(list(slections[i]))):
                            path.pop()
                    else:
                        path.pop()
                    continue
                path_all.append([area, copy.deepcopy(path)])
            self.dfs2(rects_all, S, n, idx + 1, path, path_all, limit_key, limit_value)
            if type(slections[i]) == type((1, 2)):
                for i in range(len(list(slections[i]))):
                    path.pop()
            else:
                path.pop()

    def dfs3(self, rects_all, S, n, idx, path, path_all, limit):
        if idx == n:
            return

        slections = rects_all[idx]
        if idx in limit.keys():
            slections = list(combinations(rects_all[idx], limit[idx]))

        for i in range(len(slections)):
            if type(slections[i]) == type((1, 2)):
                path.extend(list(slections[i]))
            else:
                path.append(slections[i])
            if idx == n - 1:
                area = self.getArea(path)
                if area > S:
                    if type(slections[i]) == type((1, 2)):
                        for i in range(len(list(slections[i]))):
                            path.pop()
                    else:
                        path.pop()
                    continue
                path_all.append([area, copy.deepcopy(path)])
            self.dfs3(rects_all, S, n, idx + 1, path, path_all, limit)
            if type(slections[i]) == type((1, 2)):
                for i in range(len(list(slections[i]))):
                    path.pop()
            else:
                path.pop()

    # 根据箱子面积搜索能塞下的具有最小剩余面积的rects组合
    def searchBestRects(self, S, limit):
        # 计算面积，每行按面积从小到大排序
        rects_all = []
        rect_count = 0
        for key in self.data.keys():
            rects_sub = []
            for i in range(0, len(self.data[key]), 2):
                self.keyMap[rect_count] = key + str(int(i/2 + 1))
                rects_sub.append([self.data[key][i]*self.data[key][i+1], rect_count, self.data[key][i], self.data[key][i+1]])
                rect_count += 1
            # list按面积大小从小到达排序
            rects_sub.sort()
            rects_all.append(rects_sub)

        # 按照限定总面积，找出使得具有最小剩余面积的rects组合
        self.possible_rects = []
        path = []
        self.dfs(rects_all, S, len(rects_all), 0, path, self.possible_rects)

        # # 根据limit，例如：卫浴可以继续添加一个，卧室可以继续添加两个
        # for limit_key in limit.keys():
        #     # 单种限制
        #     for limit_count in range(2,limit[limit_key] + 1, 1):
        #         new_possible_rects = []
        #         new_path = []
        #         self.dfs2(rects_all, S, len(rects_all), 0, new_path, new_possible_rects, limit_key, limit_count)
        #         self.possible_rects.extend(new_possible_rects)
        # # 组合限制
        # limit_1 = {0:2, 2:2}
        # limit_2 = {0:2, 2:3}
        # new_possible_rects = []
        # new_path = []
        # self.dfs3(rects_all, S, len(rects_all), 0, new_path, new_possible_rects, limit_1)
        # self.possible_rects.extend(new_possible_rects)
        # new_possible_rects = []
        # new_path = []
        # self.dfs3(rects_all, S, len(rects_all), 0, new_path, new_possible_rects, limit_2)
        # self.possible_rects.extend(new_possible_rects)

        # 筛选出具有最小剩余面积的模块组合
        self.possible_rects.sort(reverse=True)
        best_area = self.possible_rects[0][0]
        for v in self.possible_rects:
            if v[0] == best_area:
                self.best_rects.append(v)
            else:
                break

        # # 调试用，待删除
        # best_area = possible_rects[0][0] - 20
        # for v in possible_rects:
        #     if v[0] >= best_area - 2 and v[0] <= best_area :
        #         best_rects.append(v)
        #     elif v[0] < best_area - 2:
        #         break

        # 输出方案信息
        print("S = ", S)
        print("Total number of combinations = ", len(self.possible_rects))
        print("Best remain area = ", best_area, ", Number of best combinations = ", len(self.best_rects))
        #print(self.best_rects)
        file = open('data.txt', 'w')
        file.write("Total number of combinations = " + str(len(self.possible_rects)) + "\n")
        file.write("best remain area = " + str(best_area) + ", Number of best combinations = " + str(len(self.best_rects)) + "\n")
        file.write(str(self.best_rects))
        file.close()

    # 根据限定剩余面积搜索出符合要求的rects组合
    def searchPossibleRects(self, S, M):
        return []

    # 确认读取
    def confirmLoad(self):
        self.data = {}
        self.select = {}
        self.boxs = []
        self.iptpoints = []  # 清除本地数据

        try:
            print('confirm loading...')
            fileopen = open(self.readurl, 'r')
            k = fileopen.read()

            # 获取所有矩形、定制的矩形元素、箱子的长x宽和箱子数目
            readLines = k.split('\n')
            total = int(readLines[0])
            for i in readLines[1:total + 1]:
                location = i.split(',')
                self.data[location[0]] = list(map(float, location[2:]))
            # location = readLines[total + 1].split(',')
            # for i in location:
            #     key = i[:1]
            #     index = int(i[1:]) - 1
            #     if key not in self.select.keys():
            #         self.select[key] = [index]
            #     else:
            #         self.select[key].append(index)
            location = readLines[total + 1].split(',')
            self.boxs = list(map(float, location))
            self.boxStr = location[0] + "x" + location[1] + "x" + location[2]
            S = self.boxs[0]*self.boxs[1]*self.boxs[2]
            self.path = "results\\" + self.boxStr
            calculator.setPath(self.path)

            # 读取约束条件
            M_limit = []
            location = readLines[total + 3].split(':')
            M_limit_str = location[1].split(',')
            for v in M_limit_str:
                if '-' not in v:
                    M_limit.append(float(v))
                else:
                    tmp = v.split('-')
                    M_limit.append([float(tmp[0]), float(tmp[1])])
            calculator.setLimit(S, M_limit)

            # 计算符合占地面积要求的模块组合方案
            limit = {0:2, 2:3}      # 卫浴最多可以2个，卧室最多可以3个
            self.searchBestRects(S, limit)

            # 设置图框大小
            a = min(self.boxs[0], self.boxs[1])*self.boxs[2]
            b = max(self.boxs[0], self.boxs[1])
            calculator.setWidthHeight(max(a, b), min(a, b))
            self.l = max(a, b)
            self.h = min(a, b)
            self.scale = 350/self.l

            # # 加载选择的矩形数据
            # num = 0
            # for key in self.select.keys():
            #     gender = 0
            #     idxList = self.select[key]
            #     for idx in idxList:
            #         width = self.data[key][2 * idx]
            #         height = self.data[key][2 * idx + 1]
            #         dumped_location = [[0, 0], [width, 0], [width, height], [0, height]]
            #         if key == 'D':
            #             calculator.setRoom(num)
            #         self.iptpoints.append([num, gender, dumped_location])  # [[0, [[], [], [], []]], []]
            #         self.keyMap[num] = key + str(idx + 1)
            #         num = num + 1  # 图形编号

            # 从bestRects选择矩形数据
            for v in self.best_rects[0][1]:
                gender = 0
                num = v[1]
                width = v[2]
                height = v[3]
                dumped_location = [[0, 0], [width, 0], [width, height], [0, height]]
                self.iptpoints.append([num, gender, dumped_location])  # [[0, [[], [], [], []]], []]
                if 'D' in self.keyMap[num]:
                    calculator.setRoom(num)

            self.pushButton_3.setEnabled(True)
            self.statusBar.showMessage('    成功读取文件!!: ' + self.readurl)
        except Exception as e:
            print(e, '输入数据有问题')
            self.statusBar.showMessage('    输入的数据格式错误!!: ' + self.readurl)

        print(self.iptpoints)

    # 保存数据
    def saveData(self):
        print('saveData...')
        self.loadurl = QtWidgets.QFileDialog.getExistingDirectory(self, caption='选取存入路径', directory='../')
        print(self.loadurl)
        self.lineEdit_1.setText(self.loadurl)
        self.statusBar.showMessage('    状态：选择保存路径中...')

    # 确认保存
    def confirmSave(self):
        try:
            print('comfirm saving...')
            # 数据操作
            print(self.optpoints)

            # 数据流化
            b = ''
            for graphs in self.optpoints:
                gender = graphs[2]
                location = graphs[3]    # [[s, num, gender, [[], [], [], []]], ..]
                b = b + str(gender) + ','
                for i in range(3):
                    b = b + str(abs(location[i][0])) + ',' + str(abs(location[i][1])) + ','
                b = b.rstrip(',')
                b = b + '\n'
            b = b.rstrip('\n')  # 最后一行剪去\n

            print(b)
            fileopen = open(self.loadurl + '/物料坐标输出.csv', 'w')
            fileopen.write(b)
            self.statusBar.showMessage('    成功保存文件!!: ' + self.loadurl)
        except Exception as e:
            print(e)

    # 保持对optpoint的刷新
    def run_(self):
        calculator.downloadPossibleRects(self.possible_rects, self.best_rects, self.keyMap)

        print('running...')
        self.resume()
        self.pushButton_3.setEnabled(False) # 开始Annie
        self.pushButton_1.setEnabled(False) # 确定输入按钮
        self.pushButton_2.setEnabled(False) # 确认保存按钮

        self.startTime = time.time()   # 记录开始的时间戳
        self.pauseTime = time.time()

        self.fullLine = calculator.downloadData(self.iptpoints)

        self.__globalFlag.set()

    def clear(self):
        print('清除画布')
        calculator.clear()

        # 把图形擦掉
        self.optpoints, stop = calculator.uploadData()  # [[s, num, gender, [[], [], [], []]], ..]
        self.now = time.time()
        self.startTime = time.time()  # 记录开始的时间戳
        self.pauseTime = 0
        self.runningTime = 0
        self.update()

        #self.data.clear()
        #self.select.clear()
        #self.keyMap.clear()
        #self.pic_count = 0

        self.pushButton_1.setEnabled(True)
        self.statusBar.showMessage('    状态：清除图形成功，计算终止...（请选择 输入数据/保存数据）')

    def control(self):
        try:
            if self.__flag.is_set():    # 暂停
                self.pause()
                self.pauseTime = self.now - self.startTime  # 上次运行所用时间
            else:
                self.runningTime = self.runningTime + self.pauseTime    # 将上次运行的对齐到现在时间
                self.resume()
                self.startTime = time.time()
        except Exception as e:
            print(e)

        # 清除
        self.clear()
        # # 确定
        # self.confirmLoad()
        # 开始
        self.run_()

    def resume(self):
        #self.pushButton.setText('暂停')
        self.pushButton_4.setEnabled(False)
        self.statusBar.showMessage('    状态：计算中...')
        self.__flag.set()   # T
        calculator.resume()

    def pause(self):
        #self.pushButton.setText('继续')
        self.pushButton_4.setEnabled(True)
        #self.statusBar.showMessage('    状态：暂停中...')

        self.__flag.clear()
        calculator.pause()

    def refreshData(self):
        calculator.StartDraw.wait()
        #self.pause()    # 初始化就启动程序，但不开始扫描
        while self.__running.isSet():
            self.__flag.wait()
            calculator.RedrawFlag.wait()

            #time.sleep(self.timeInterval)

            try:
                # 实时更新数据
                self.optpoints, stop = calculator.uploadData()    # [[s, num, gender, [[], [], [], []]], ..]
                self.optpoints.reverse()
                if len(self.optpoints)>0 and len(self.optpoints) != 1 and self.optpoints[0][1] == self.optpoints[1][1]:
                    self.optpoints.pop(0)

                # # 刷新时间
                # self.now = time.time() # 记录现在时间戳
                # k = time.localtime(self.now - self.startTime + self.runningTime)
                #self.label_2.setText('用时:' + str(time.strftime('%M:%S', k)))

                self.update()
                self.pushButton_2.setEnabled(True)

                # 保存截图
                pic = ImageGrab.grab((1100, 450, 1500, 850))
                pic.save(self.path + "\\" + str(calculator.pic_count) + ".jpg")
                # 延迟一定时间用于图片保存
                time.sleep(0.5)
                # 关闭视图刷新
                calculator.RedrawFlag.clear()
                # 通知计算程序可以继续计算
                calculator.RedrawOver.set()
            except Exception as e:
                print(e)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    mywin = MyWindow()
    mywin.show()

    sys.exit(app.exec_())

