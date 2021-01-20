# -*- coding: utf-8 -*-

import copy,sys,time,os,shutil
import threading
import numpy as np

# from shapely.geometry import geo, polygon
# from shapely.geos import pointer

class pack_1D():
    # getBestRect(): 传入横轴方向上最大连续空白长度和待排列的矩形集合
    # 返回：answer={num, length}, 即最适合的矩形id，length可能是长度也可能是宽度，据此判断是横放还是竖放。answer为空说明放不下。
    def getBestRect(self, blank, rects):
        self.rects = rects  # 待计算矩形: # [[s, num, gender, [[], [], [], []]], ..]
        self.blank = blank  # 空白区域长度
        self.bestFit = blank  # 最小缝隙(排列矩形思路：选择使得底部缝隙最小的矩形优先排列)
        self.answer = {}  # 计算结果：{num:长或宽, ...}
        self.rollAnswer = {}  # 计算中的结果
        self.area = 0
        self.rollArea = 0

        # 返回一组排列，这组排列能够使得留下的缝隙尽可能小，相同剩余缝隙下选择组合面积更大的排列方案输出
        self._go(self.blank, self.rects)
        return self.answer

    def _go(self, blank, rects):
        if blank < self.bestFit:  # 这轮排列的矩形产生了更小的缝隙，则对answer进行更新
            self.bestFit = blank
            self.answer = self.rollAnswer.copy()  # 复制rollAnswer路径

        elif blank == self.bestFit and self.rollArea > self.area:  # 如果产生的缝隙相等，并且该轮排列矩形的面积更大，也将进行answer更新
            self.area = self.rollArea
            self.bestFit = blank
            self.answer = self.rollAnswer.copy()

        if not rects:
            return 0

        # 遍历每一个矩形，计算每个矩形横放和竖放后产生的横向缝隙，越小越好，如果相等，则矩形面积累加越大越好
        # 同时排列一个矩形之后，如果留有空隙，则继续利用剩余空隙进行排列，直至空隙 < 0
        for i in range(len(rects)):  # [[s, num, gender, [[], [], [], []]], ..]

            s = rects[i][0]
            num = rects[i][1]
            gender = rects[i][2]
            graph = rects[i][3]  # 第i个矩形
            l = graph[2][0] - graph[0][0]  # 第i个矩形的长度
            h = graph[2][1] - graph[0][1]  # 第i个矩形高度
            new_rects = rects.copy()
            for j in range(i + 1):
                new_rects.pop(0)  # new_rects是剔除前i个矩形后的集合

            self.rollAnswer[num] = l  # 选择横放：lxh
            self.rollArea += s
            new_blank = blank - l  # 剩余空白长度-第i个矩形的长度

            if new_blank >= 0:  # 只有当空白足够放置，rollAnswer才有机会留存
                self._go(new_blank, new_rects)  # 递归利用剩余缝隙在剩余矩形集合中继续选择矩形进行排列(每次有可能是横放，也可能是竖放)，直至缝隙 < 0

            self.rollAnswer.pop(num)  # 回溯：撤销前面的修改
            self.rollArea -= s

            self.rollAnswer[num] = h  # 选择竖放：hxl
            self.rollArea += s
            new_blank = blank - h  # 剩余空白长度-第i个矩形的高度

            if new_blank >= 0:  # 只有空白足够放置，rollAnswer才有机会留存
                self._go(new_blank, new_rects)  # 递归利用剩余缝隙在剩余矩形集合中继续选择矩形进行排列，直至缝隙 < 0

            self.rollAnswer.pop(num)  # 回溯：撤销前面的修改
            self.rollArea -= s


'''通过threading.Event()可以创建一个事件管理标志，该标志（event）默认为False，event对象主要有四种方法可以调用：
    event.wait(timeout=None)：调用该方法的线程会被阻塞，如果设置了timeout参数，超时后，线程会停止阻塞继续执行；
    event.set()：将event的标志设置为True，调用wait方法的所有线程将被唤醒；
    event.clear()：将event的标志设置为False，调用wait方法的所有线程将被阻塞；
    event.isSet()：判断event的标志是否为True。
'''


class Calculator(threading.Thread, pack_1D):
    def __init__(self):
        super(Calculator, self).__init__()
        self.__flag = threading.Event()
        self.__flag.set()
        self.__globalFlag = threading.Event()
        self.__globalFlag.clear()
        self.__running = threading.Event()
        self.__running.set()

        self.room = 0   # 客厅标识
        self.room_points = []   # 客厅位置
        self.mutex = threading.Lock()     # 对optpoints增加互斥锁，main一直在多线程读取，防止读写冲突
        self.possible_rects = []
        self.best_rects = []
        self.keyMap = {}
        self.interval = 1000
        self.gen_limit = self.interval
        self.succeed = 0
        self.idx = 0
        self.path = ""
        self.remain_area = 0

        # 为了筛选
        self.S = 0
        self.M_limit = []
        self.ValidRects = []
        self.RedrawFlag = threading.Event()
        self.RedrawFlag.clear()
        self.RedrawOver = threading.Event()
        self.RedrawOver.clear()
        self.StartDraw = threading.Event()
        self.StartDraw.clear()
        self.pic_count = 0

        self.iptpoints = []  # 读取的数据点:[[s, num, gender, [[], [], [], []]], ..]
        self.optpoints = [[0, 0, -1, [[0, 0], [0, 0], [0, 0]]]]  # 输出的数据点:[[s, num, gender, [[], [], [], []]], ..]
        self.rects = []  # [[s, num, gender, [[], [], [], []]], ..]
        self.tris = []  # [[s, num, gender, [[], [], [], []]], ..]
        self.virticalTris = []  # [[s, num, gender, [[], [], [], []]], ..]
        self.grids = {}  # 栅格:0代表未使用，1代表使用
        self.settledPoints = []  # 已经排好的图形：[[Yc, y_max, Xc, gender, location, num, s], ..]
        self.y_full = 0  # 传入所有图形拼整以40为底后的最高线，最终结果肯定是高于这个线的，主要用来区分什么时候用什么排样模式
        self.y_max = 0  # 排布时图形现在的最高线
        self.y_list = []  # 存放seetledpoint的所有Y坐标：[[y_max, num], [], []..]
        self.pastPoint = []
        self.bestChoice = []  # 回溯的最好选择:[[Yc, y_max, Xc, gender, location, num, s], ..]

        self.finishFlag = False  # 计算结束表示
        self.stopFlag = False  # 计算终止表示
        self.numScale = 3  # 小数四舍五入位数,推荐：3，4
        self.sleepTime = 0  # 睡眠时间,用来调整计算速度，推荐：1，0.001，0
        self.roundScale = 180  # 每次旋转的刻度,推荐：如4代表每次旋转90°，8代表每次旋转45°
        self.gridScale = 10  # 遍历时使用的栅格的放大倍数
        self.gridX = 40.0  # 排布时的X范围
        self.gridY = 50.0  # Y

    def setRoom(self,idx):
        self.room = idx

    def setLimit(self, S, M_limit):
        self.S = S
        self.M_limit = M_limit

    def setWidthHeight(self,width,height):
        self.gridX = width
        self.gridY = height

    def initGrid(self):
        '''
        简历40×50网格
        :return:
        '''
        k = np.zeros((int(self.gridX * self.gridScale) + 1) * (int(self.gridY * self.gridScale) + 1)).reshape(
            [int(self.gridX * self.gridScale) + 1, int(self.gridY * self.gridScale) + 1])
        k[0] = 0.5
        k[-1] = 0.5
        k.T[0] = 0.5
        k.T[-1] = 0.5
        self.grids = k

    def judgeValid(self, try_idx, needDraw=False):
        try:
            # 初始模块组合方案
            self.clear()
            self.initNewIptpoints(try_idx)

            # ====================排列矩形====================
            source_rects = self.rects
            gen = 0
            while (len(self.optpoints) < len(source_rects) + 1):
                self.rects = source_rects
                # 获取互斥锁后，进程只能在释放锁后下个进程才能进来
                self.mutex.acquire()
                self.optpoints = [[0, 0, -1, [[0, 0], [0, 0], [0, 0]]]]
                # 互斥锁必须被释放掉
                self.mutex.release()
                self.settledPoints.clear()
                self.initGrid()
                self.place_rect_rand(needDraw)
                gen = gen + 1
                if gen > self.gen_limit:
                    break
            # ====================排列矩形====================

            if gen <= self.gen_limit:
                print("gen = ", gen, ", isValid = true")
                return True

            print("gen = ", gen, ", isValid = false")
            return False
        except Exception as e:
            print("judgeValid error: ", e)

    # 预估可排列的组合方案数P1
    def stage_1(self):
        try:
            total = len(self.possible_rects)
            try_count = 0
            try_idx = 0
            high_idx = total - 1
            low_idx = 0

            # 判断最头部元素
            try_count = try_count + 1
            print("try_count = ", try_count)
            if self.judgeValid(try_idx):
                return total

            flag = False
            while(low_idx < high_idx - 1):
                try_count = try_count + 1
                print("try_count = ", try_count)
                try_idx = int((low_idx + high_idx) / 2)
                flag = self.judgeValid(try_idx)
                if flag:    # idx可行，则需要向前面继续探索
                    high_idx = try_idx
                else:       # idx不可行，则需要向后面继续探索
                    low_idx = try_idx

            return total - low_idx + 1
        except Exception as e:
            print("stage_1 error: ", e)

    def lower_bound(self, data, x, idx):
        try:
            left = 0
            right = len(data) - 1
            while(left < right):
                mid = int((left + right) / 2)
                if data[mid][0] == x:
                    right = right - 1
                elif data[mid][0] > x:
                    left = mid + 1
                else:
                    right = mid - 1

            return min(left, len(data) - 1) + idx
        except Exception as e:
            print("lower_bound error: ", e)

    def upper_bound(self, data, x, idx):
        try:
            left = 0
            right = len(data) - 1
            while (left < right):
                mid = int((left + right) / 2)
                if data[mid][0] == x:
                    left = left + 1
                elif data[mid][0] > x:
                    left = mid + 1
                else:
                    right = mid - 1

            return max(right, 0) + idx
        except Exception as e:
            print("upper_bound error: ", e)

    # 根据剩余面积约束继续筛选
    def stage_2(self, total_valid):
        try:
            # 优先筛选最小剩余面积的组合方案数
            idx = len(self.possible_rects) - total_valid
            valid_area = self.possible_rects[idx][0]
            valid_count = 0
            for v in self.possible_rects[idx:]:
                if v[0] == valid_area:
                    valid_count = valid_count + 1
                else:
                    break
            print("The number of feasible solutions with minimum remaining area = ", valid_count, ", the area = ", valid_area)

            # 根据M_limit筛选符合要求的组合方案数
            for M in self.M_limit:
                valid_rects = []
                if type(M) == type(1.0):     # 指定剩余面积阈值，输出刚好等于，如果没有则输出最靠近的
                    valid_area = self.S - M
                    low_idx = self.lower_bound(self.possible_rects[idx:], valid_area, idx)
                    high_idx = self.upper_bound(self.possible_rects[idx:], valid_area, idx)
                    valid_count = high_idx - low_idx + 1
                    for i in range(low_idx, high_idx + 1):
                        valid_rects.append([i, self.possible_rects[i]])
                    self.ValidRects.append(valid_rects)
                    print("The number of feasible solutions with specified remaining area (", M, ") = ", valid_count, ", the area = ", self.possible_rects[low_idx][0])
                elif type(M) == type([1,2]):   # 指定剩余面积是一个范围，输出处于该范围的所有组合方案数
                    high_bound = self.S - M[0]
                    low_bound = self.S - M[1]
                    low_idx = self.lower_bound(self.possible_rects[idx:], high_bound, idx)
                    high_idx = self.upper_bound(self.possible_rects[idx:], low_bound, idx)
                    valid_count = high_idx - low_idx + 1
                    for i in range(low_idx, high_idx + 1):
                        valid_rects.append([i, self.possible_rects[i]])
                    self.ValidRects.append(valid_rects)
                    print("The number of feasible solutions with specified remaining area [", M[0], ",", M[1], "] = ", valid_count, ", the area = [", low_bound, ",",high_bound,"]")
        except Exception as e:
            print("stage_2 error: ", e)

    # 对少于100的组合方案，a).每个组合搜索出一种排列并输出数据到文件保存，b).可视化图例进行截图保存
    def stage_4(self):
        try:
            if os.path.exists(self.path) == True:   # 删除已有目录
                shutil.rmtree(self.path)    #空目录、有内容的目录都可以删
            os.mkdir(self.path)  # 创建空目录
            file_path = self.path + "\\result.csv"
            open(file_path, mode='w')   # 打开一个文件只用于写入。如果该文件已存在则打开文件，并从开头开始编辑，即原有内容会被删除。如果该文件不存在，创建新文件。
            with open(file_path, mode='a') as filename:
                res = "image_id, usage, remain_area, combination, arrangement\n"
                filename.write(res)
            ans_count = 0
            for i in range(len(self.ValidRects)):
                valid_rects = self.ValidRects[i]
                if len(valid_rects) > 100:
                    continue

                print("now search M_limit = ", self.M_limit[i], ", valid_rects number = ", len(valid_rects))

                if ans_count > 0:
                    file_path = self.path + "\\result.csv"
                    with open(file_path, mode='a') as filename:
                        filename.write("\n")

                # 搜索每个组合的排列，并输出排列结果
                for j in range(len(valid_rects)):
                    v = valid_rects[j]
                    try_idx = v[0]
                    self.remain_area = self.S - v[1][0]
                    flag = self.judgeValid(try_idx, True)
                    print("try_idx = ", try_idx, ", searched = ", flag)
                ans_count = ans_count + 1

            # 处理最后一张图片的延迟
            time.sleep(1)
            # 通知刷新视图
            self.RedrawFlag.set()
            # 等待刷新完成之后再跳出
            self.RedrawOver.wait()
            self.RedrawOver.clear()

            # 删除无效的"0.jpg"
            filepath = self.path + "\\0.jpg"
            if os.path.isfile(filepath):
                os.remove(filepath)
        except Exception as e:
            print("stage_4 error: ", e)

    def calculating(self):
        '''
        更新optpoints
        :return:
        '''
        #print('开始计算')
        np.random.seed()  # RandomState生成随机数种子

        # ====================阶段1：预估可排列的组合方案数P1：采用二分搜索算法=========================================================
        total_valid = self.stage_1()
        print("The number of feasible solutions that can be arranged in the box = ", total_valid)

        # ====================阶段2：根据剩余面积约束搜索P1中符合要求的组合方案数P2======================================================
        self.stage_2(total_valid)

        # ====================阶段3：在P2上继续添加多目标的约束，缩窄组合方案数范围到100个，设为P4=======================================


        # ====================阶段4：搜索P4中各种可能的排列，可以对每个组合设定一个排列方案限定数目，输出排列视图和详细数据==============
        self.StartDraw.set()
        self.stage_4()

        return

    def randPos(self, low, high):
        a = np.random.uniform(low, high)  # 随机数范围
        return round(a/self.gridScale,1)

    # 根据rect左下角点构建坐标：客厅、右边探索、上方探索
    def getGraphByLeftDown(self, l, h, pos_x, pos_y):
        new_graph = [[pos_x , pos_y ], [pos_x + l, pos_y ],
                     [pos_x + l , pos_y + h ], [pos_x , pos_y + h ]]
        return new_graph

    # 根据rect左上角点构建坐标：下方探索
    def getGraphByLeftTop(self, l, h, pos_x, pos_y):
        new_graph = [[pos_x , pos_y - h ], [pos_x + l, pos_y - h ],
                     [pos_x + l , pos_y ], [pos_x , pos_y ]]
        return new_graph

    # 根据rect右下角点构建坐标：左边探索
    def getGraphByRightDown(self, l, h, pos_x, pos_y):
        new_graph = [[pos_x - l, pos_y], [pos_x , pos_y ],
                     [pos_x , pos_y + h], [pos_x - l, pos_y + h]]
        return new_graph

    def place_living_room(self):
        try:
            # 1.找出客厅，计算坐标，插入绘图
            room_rect = []
            for v in self.rects:
                if v[1] == self.room:  # 找出客厅
                    room_rect = v
                    break
            # 计算客厅坐标
            graph = room_rect[3]
            l = graph[2][0] - graph[0][0]  # 长度
            h = graph[2][1] - graph[0][1]  # 高度

            # # 固定位置：图框中心
            # pos_x = round(self.gridX / 2 - l / 2, 1)
            # pos_y = round(self.gridY / 2 - h / 2, 1)
            # new_graph = [[pos_x , pos_y ], [pos_x + l, pos_y ],
            #             [pos_x + l , pos_y + h ], [pos_x , pos_y + h ]]

            # 随机探索客厅左下角点的可行位置
            low_x = 0
            high_x = int((self.gridX - l)*self.gridScale)
            low_y = 0
            high_y = int((self.gridY - h)*self.gridScale)
            pos_x = self.randPos(low_x, high_x )
            pos_y = self.randPos(low_y, high_y )
            new_graph = self.getGraphByLeftDown(l, h, pos_x, pos_y)

            # Xc, Yc分别是所放置矩形的形心(矩形各节点坐标求均值所得)横坐标和纵坐标，y_max是矩形各节点坐标在纵向上的最大高度
            Xc, Yc, y_max = self.caculateCenter(0, new_graph)  # 旋转后的形心
            # 刷新正在排样的图形：往已有视图中添加该矩形
            self.refreshData([Yc, y_max, Xc, 0, new_graph, room_rect[1], room_rect[0]],
                             save=True)  # [[Yc, y_max, Xc, gender, location, num, s],..]
            self.saveData([Yc, y_max, Xc, 0, new_graph, room_rect[1], room_rect[0]])
            self.bestChoice = copy.deepcopy(self.settledPoints)  # 保存排列结果, [[Yc, y_max, Xc, gender, location, num, s], ..]
            self.room_points = self.bestChoice[0]
        except Exception as e:
            print("place_living_room error: ", e)

    def getLeftSpace(self, room_graph, rect_width, rect_height):
        all_sub_answer = []

        try:
            # 搜索与客厅左边接触的可行空间：游标是rect的右下角点
            start_x = room_graph[0][0]
            start_y = max(room_graph[0][1] - (rect_height - 0.9), 0)
            cursor_x = round(start_x * self.gridScale)
            last_valid = -1
            sub_answer = []
            for cursor_y in range(round(start_y * self.gridScale), round((room_graph[3][1] - 0.9) * self.gridScale) + 1):
                if start_x < rect_width:
                    break  # 探索区域容不下rect，直接退出

                # 判断当前角点pos是否合法，更新可行区间
                isValid = True
                if cursor_y + round(rect_height * self.gridScale) > self.gridY* self.gridScale:
                    isValid = False
                else:
                    for cursor in range(cursor_y, cursor_y + round(rect_height * self.gridScale) + 1):
                        if self.grids[cursor_x - 1, cursor] == 1:
                            isValid = False
                            break
                if isValid:
                    if last_valid < 0:  # 创建新的answer区间
                        sub_answer = [cursor_x, cursor_x, cursor_y, cursor_y]
                        last_valid = cursor_y
                    else:  # 更新answer区间
                        sub_answer[3] = cursor_y
                else:
                    if last_valid >= 0:  # 保存answer区间，并将last_valid复位
                        last_valid = -1
                        all_sub_answer.append(sub_answer)

                # 遍历到终点需要额外判断一次：游标是rect的左下角点
                if isValid and cursor_y == round((room_graph[3][1] - 0.9) * self.gridScale):
                    all_sub_answer.append(sub_answer)

            return all_sub_answer
        except Exception as e:
            print("getLeftSpace error: ", e)

    def getTopSpace(self, room_graph, rect_width, rect_height):
        all_sub_answer = []

        try:
            # 搜索与客厅上边接触的可行空间：游标是rect的左下角点
            start_x = max(room_graph[3][0] - (rect_width - 0.9), 0)
            start_y = room_graph[3][1]
            cursor_y = round(start_y * self.gridScale)
            last_valid = -1
            sub_answer = []
            for cursor_x in range(round(start_x * self.gridScale), round((room_graph[2][0] - 0.9) * self.gridScale) + 1):
                if self.gridY - start_y < rect_height:
                    break  # 探索区域容不下rect，直接退出

                # 判断当前角点pos是否合法，更新可行区间
                isValid = True
                if cursor_x + round(rect_width * self.gridScale) > self.gridX* self.gridScale:
                    isValid = False
                else:
                    for cursor in range(cursor_x, cursor_x + round(rect_width * self.gridScale) + 1):
                        if self.grids[cursor, cursor_y + 1] == 1:
                            isValid = False
                            break
                if isValid:
                    if last_valid < 0:  # 创建新的answer区间
                        sub_answer = [cursor_x, cursor_x, cursor_y, cursor_y]
                        last_valid = cursor_x
                    else:  # 更新answer区间
                        sub_answer[1] = cursor_x
                else:
                    if last_valid >= 0:  # 保存answer区间，并将last_valid复位
                        last_valid = -1
                        all_sub_answer.append(sub_answer)

                # 遍历到终点需要额外判断一次：游标是rect的左下角点
                if isValid and cursor_x == round((room_graph[2][0] - 0.9) * self.gridScale):
                    all_sub_answer.append(sub_answer)

            return all_sub_answer
        except Exception as e:
            print("getTopSpace error: ", e)

    def getRightSpace(self, room_graph, rect_width, rect_height):
        all_sub_answer = []

        try:
            # 搜索与客厅右边接触的可行空间：游标是rect的左下角点
            start_x = room_graph[1][0]
            start_y = max(room_graph[1][1] - (rect_height - 0.9), 0)
            cursor_x = round(start_x * self.gridScale)
            last_valid = -1
            sub_answer = []
            for cursor_y in range(round(start_y * self.gridScale), round((room_graph[2][1] - 0.9) * self.gridScale) + 1):
                if self.gridX - start_x < rect_width:
                    break  # 探索区域容不下rect，直接退出

                # 判断当前角点pos是否合法，更新可行区间
                isValid = True
                if cursor_y + round(rect_height * self.gridScale) > self.gridY* self.gridScale:
                    isValid = False
                else:
                    for cursor in range(cursor_y, cursor_y + round(rect_height * self.gridScale) + 1):
                        if self.grids[cursor_x + 1, cursor] == 1:
                            isValid = False
                            break
                if isValid:
                    if last_valid < 0:  # 创建新的answer区间
                        sub_answer = [cursor_x, cursor_x, cursor_y, cursor_y]
                        last_valid = cursor_y
                    else:  # 更新answer区间
                        sub_answer[3] = cursor_y
                else:
                    if last_valid >= 0:  # 保存answer区间，并将last_valid复位
                        last_valid = -1
                        all_sub_answer.append(sub_answer)

                # 遍历到终点需要额外判断一次：游标是rect的左下角点
                if isValid and cursor_y == round((room_graph[2][1] - 0.9) * self.gridScale):
                    all_sub_answer.append(sub_answer)

            return all_sub_answer
        except Exception as e:
            print("getRightSpace error: ", e)

    def getDownSpace(self, room_graph, rect_width, rect_height):
        all_sub_answer = []

        try:
            # 搜索与客厅下边接触的可行空间：游标是rect的左上角点
            start_x = max(room_graph[0][0] - (rect_width - 0.9), 0)
            start_y = room_graph[0][1]
            cursor_y = round(start_y * self.gridScale)
            last_valid = -1
            sub_answer = []
            for cursor_x in range(round(start_x * self.gridScale), round((room_graph[1][0] - 0.9) * self.gridScale) + 1):
                if start_y < rect_height:
                    break  # 探索区域容不下rect，直接退出

                # 判断当前角点pos是否合法，更新可行区间
                isValid = True
                if cursor_x + round(rect_width * self.gridScale) > self.gridX* self.gridScale:
                    isValid = False
                else:
                    for cursor in range(cursor_x, cursor_x + round(rect_width * self.gridScale) + 1):
                        if self.grids[cursor, cursor_y] == 1:
                            isValid = False
                            break
                if isValid:
                    if last_valid < 0:  # 创建新的answer区间
                        sub_answer = [cursor_x, cursor_x, cursor_y, cursor_y]
                        last_valid = cursor_x
                    else:  # 更新answer区间
                        sub_answer[1] = cursor_x
                else:
                    if last_valid >= 0:  # 保存answer区间，并将last_valid复位
                        last_valid = -1
                        all_sub_answer.append(sub_answer)

                # 遍历到终点需要额外判断一次：游标是rect的左下角点
                if isValid and cursor_x == round((room_graph[1][0] - 0.9) * self.gridScale):
                    all_sub_answer.append(sub_answer)

            return all_sub_answer
        except Exception as e:
            print("getDownSpace error: ", e)

    # 返回{0:{["down":[low_x, high_x, low_y, high_y],...];"right":[[xxx]...];1:[xxx...]}}，每个元素竖放的可行域空间，和横放的可行域空间
    def searchValidSpace(self, rect_width, rect_height):
        answer = {}
        # 游标从客厅左下角出发，绕行四个方向，判断四个可行空间
        room_graph = self.room_points[4]

        for i in range(2):
            # ====================i=0:竖放矩形====================
            if i == 0:
                answer[0] = {}
            # ====================i=1:横放矩形====================
            if i == 1:
                rect_width, rect_height = rect_height, rect_width
                answer[1] = {}

            # 搜索与客厅下边接触的可行空间：游标是rect的左上角点
            answer[i]["down"] = self.getDownSpace(room_graph, rect_width, rect_height)

            # 搜索与客厅右边接触的可行空间：游标是rect的左下角点
            answer[i]["right"] = self.getRightSpace(room_graph, rect_width, rect_height)

            # 搜索与客厅上边接触的可行空间：游标是rect的左下角点
            answer[i]["top"] = self.getTopSpace(room_graph, rect_width, rect_height)

            # 搜索与客厅左边接触的可行空间：游标是rect的右下角点
            answer[i]["left"] = self.getLeftSpace(room_graph, rect_width, rect_height)


        # 返回可行空间
        return answer

    # 在所有可行区间中公平随机选中一个区间，返回：例如{"down":[low_x,high_x,low_y,high_y]}
    def selectOneSpace(self, answer):
        # 选中概率依照各个区间长度：选择横放/竖放->选择上/下/左/右->选择具体区间
        select = []
        select_num = 0
        select_fun = "down"

        try:
            # 紧凑输出
            if len(answer[0]["down"]) > 0:
                select = [0, "down", answer[0]["down"][0]]
            elif len(answer[1]["down"]) > 0:
                select = [1, "down", answer[1]["down"][0]]
            elif len(answer[0]["right"]) > 0:
                select = [0, "right", answer[0]["right"][0]]
            elif len(answer[1]["right"]) > 0:
                select = [1, "right", answer[1]["right"][0]]
            elif len(answer[0]["top"]) > 0:
                select = [0, "top", answer[0]["top"][len(answer[0]["top"])-1]]
            elif len(answer[1]["top"]) > 0:
                select = [1, "top", answer[1]["top"][len(answer[0]["top"])-1]]
            elif len(answer[0]["left"]) > 0:
                select = [0, "left", answer[0]["left"][len(answer[0]["left"])-1]]
            elif len(answer[1]["left"]) > 0:
                select = [1, "left", answer[1]["left"][len(answer[0]["left"])-1]]

            return select

            # 统计区间长度
            length_count_all = [0, 0]
            length_count_sub = {0: [0, 0, 0, 0], 1: [0, 0, 0, 0]}
            for i in range(2):
                for v in answer[i]["down"]:
                    length_count_all[i] += v[1] - v[0] + v[3] - v[2]
                    length_count_sub[i][0] += v[1] - v[0] + v[3] - v[2]
                for v in answer[i]["right"]:
                    length_count_all[i] += v[1] - v[0] + v[3] - v[2]
                    length_count_sub[i][1] += v[1] - v[0] + v[3] - v[2]
                for v in answer[i]["top"]:
                    length_count_all[i] += v[1] - v[0] + v[3] - v[2]
                    length_count_sub[i][2] += v[1] - v[0] + v[3] - v[2]
                for v in answer[i]["left"]:
                    length_count_all[i] += v[1] - v[0] + v[3] - v[2]
                    length_count_sub[i][3] += v[1] - v[0] + v[3] - v[2]

            # 如果可行空间不存在，直接退出
            length_sum = length_count_all[0] + length_count_all[1]
            if length_sum == 0:
                return select

            # 1.选择摆放方向
            rand_t_1 = np.random.random()  #0-1之间抽样随机数
            if rand_t_1 <= length_count_all[0] / length_sum:
                select_num = 0
            else:
                select_num = 1

            # 2.选择上/下/左/右
            rand_t_2 = np.random.random()  # 0-1之间抽样随机数
            a = sum(length_count_sub[select_num][:1]) / length_count_all[select_num]
            if rand_t_2 >=0 and rand_t_2 <= sum(length_count_sub[select_num][:1]) / length_count_all[select_num]:
                select_fun = "down"
            elif rand_t_2 > sum(length_count_sub[select_num][:1]) / length_count_all[select_num] and rand_t_2 <= sum(length_count_sub[select_num][:2]) / length_count_all[select_num]:
                select_fun = "right"
            elif rand_t_2 > sum(length_count_sub[select_num][:2]) / length_count_all[select_num] and rand_t_2 <= sum(length_count_sub[select_num][:3]) / length_count_all[select_num]:
                select_fun = "top"
            elif rand_t_2 > sum(length_count_sub[select_num][:3]) / length_count_all[select_num] and rand_t_2 <= 1:
                select_fun = "left"

            # 3.选择具体区间
            length_count = []
            for v in answer[select_num][select_fun]:
                length_count.append(v[1] - v[0] + v[3] - v[2])
            rand_t_3 = np.random.random()  # 0-1之间抽样随机数
            for i in range(len(length_count)):
                if rand_t_3>= sum(length_count[:i]) / sum(length_count) and rand_t_2 <= sum(length_count[:i + 1]) / sum(length_count):
                    select = [select_num, select_fun, answer[select_num][select_fun][i]]
                    break

            if len(select) == 0:
                check = True
            return select
        except Exception as e:
            print("selectOneSpace error: ", e)

    def setPath(self,path):
        self.path = path

    # 保存当前排列数据：id，利用率，剩余面积，组合列表，排列数据
    def saveResult(self):
        try:
            file_path = self.path + "\\result.csv"
            with open(file_path, mode='a') as filename:   # mode='a'，即追加（append）模式，mode=' r' 则为读（read).
                res = str(self.pic_count + 1) + "," + str(round(1 - self.remain_area / self.S, 4) * 100) + "%," + str(self.remain_area) + ",\""
                for i in range(len(self.rects)):
                    if i > 0:
                        res = res + ","
                    v = self.rects[i]
                    res  = res + self.keyMap[v[1]]
                res = res + "\",\"{"
                for k in range(len(self.bestChoice)):   # [[Yc, y_max, Xc, gender, location, num, s], ..]
                    if k > 0:
                        res = res + ","
                    v = self.bestChoice[k]
                    res = res + self.keyMap[v[5]] + ":"
                    res = res + "["
                    for i in range(len(v[4])):
                        if i > 0:
                            res = res + ","
                        points = [round(v[4][i][0], 1), round(v[4][i][1], 1)]
                        res = res + str(points)    # 坐标以0.1为模数
                    res = res + "]"
                res = res + "}\"\n"
                filename.write(res)
        except Exception as e:
            print("saveResult error: ", e)

    def place_rect_rand(self, needDraw=False):
        try:
            # 1.在客厅的可行解空间随机选取一个位置放置
            self.place_living_room()

            # 2.利用GA算法打乱后续元素的排列顺序
            remain_rects = []
            for v in self.rects:
                if v[1] != self.room:  # 找出客厅
                    remain_rects.append(v)
            arr = np.array(range(0, len(remain_rects), 1))
            np.random.shuffle(arr)  # 暂时使用随机打乱顺序，后续使用GA，但是困扰是GA优化的目标是什么？

            # 3.按照排列顺序，对于当前排列的每个元素，在其可行解空间中随机选取一个位置放置
            Succeed = True
            for i in arr:
                rect = remain_rects[i]
                #print(rect)
                graph = rect[3]
                l = graph[2][0] - graph[0][0]  # 长度
                h = graph[2][1] - graph[0][1]  # 高度
                # 随机探索可行位置：找出围绕客厅的4个可行域(无可行域时此轮方案直接结束，重新从客厅开始)->随机选定一个可行域->使用randPos选定摆放位置。
                answer = self.searchValidSpace(l,h)
                #print("answer: ", answer)
                if self.keyMap[rect[1]] == "F1":    # 阳台必须沿着最长边摆放
                    # 不允许摆放的区间
                    answer[1]["down"] = []
                    answer[0]["right"] = []
                    answer[1]["top"] = []
                    answer[0]["left"] = []
                    # 允许摆放的区间必须长边全部接触
                    valid_spqce = []
                    min_x = round(self.room_points[4][0][0]*self.gridScale)
                    max_x = round((self.room_points[4][1][0] - l)*self.gridScale)
                    min_y = round(self.room_points[4][0][1]*self.gridScale)
                    max_y = round((self.room_points[4][3][1] - h)*self.gridScale)
                    for k in answer[0]["down"]: # 左上角点
                        if (k[0] > max_x or k[1] < min_x) == False:
                            valid_spqce.append([max(k[0], min_x), min(k[1], max_x), k[2], k[3]])
                    answer[0]["down"] = valid_spqce
                    valid_spqce = []
                    for k in answer[1]["right"]: # 左下角点
                        if (k[2] > max_y and k[3] < min_y) == False:
                            valid_spqce.append([k[0], k[1], max(k[2], min_y), min(k[3], max_y)])
                    answer[1]["right"] = valid_spqce
                    valid_spqce = []
                    for k in answer[0]["top"]: # 左下角点
                        if (k[0] > max_x or k[1] < min_x) == False:
                            valid_spqce.append([max(k[0], min_x), min(k[1], max_x), k[2], k[3]])
                    answer[0]["top"] = valid_spqce
                    valid_spqce = []
                    for k in answer[1]["left"]: # 右下角点
                        if (k[2] > max_y and k[3] < min_y) == False:
                            valid_spqce.append([k[0], k[1], max(k[2], min_y), min(k[3], max_y)])
                    answer[1]["left"] = valid_spqce

                select = self.selectOneSpace(answer)
                #print("select: ", select)

                # 如果可行空间不存在，直接退出
                if len(select) == 0:
                    Succeed = False
                    break

                # 根据select的区间随机选定rect位置
                pos_x = self.randPos(select[2][0], select[2][1])
                pos_y = self.randPos(select[2][2], select[2][3])
                if select[0] == 1:  # 选择横放
                    l, h  = h, l
                new_graph = []
                if select[1] == "down":
                    new_graph = self.getGraphByLeftTop(l, h, pos_x, pos_y)
                elif select[1] == "right":
                    new_graph = self.getGraphByLeftDown(l, h, pos_x, pos_y)
                elif select[1] == "top":
                    new_graph = self.getGraphByLeftDown(l, h, pos_x, pos_y)
                elif select[1] == "left":
                    new_graph = self.getGraphByRightDown(l, h, pos_x, pos_y)
                # Xc, Yc分别是所放置矩形的形心(矩形各节点坐标求均值所得)横坐标和纵坐标，y_max是矩形各节点坐标在纵向上的最大高度
                Xc, Yc, y_max = self.caculateCenter(0, new_graph)  # 旋转后的形心
                # 刷新正在排样的图形：往已有视图中添加该矩形
                self.refreshData([Yc, y_max, Xc, 0, new_graph, rect[1], rect[0]],
                                 save=True)  # [[Yc, y_max, Xc, gender, location, num, s],..]
                self.saveData([Yc, y_max, Xc, 0, new_graph, rect[1], rect[0]])
                self.bestChoice = copy.deepcopy(self.settledPoints)  # 保存排列结果

            if needDraw and Succeed:
                # 保存排列数据
                self.saveResult()
                # 通知刷新视图
                self.RedrawFlag.set()
                # 等待刷新完成之后再跳出
                self.RedrawOver.wait()
                self.RedrawOver.clear()
                self.pic_count += 1
        except Exception as e:
            print("place_rect_rand error: ", e)

    # 形心/三个点的y值和最低
    def caculateCenter(self, gender, location=None):
        '''
        lei为图形的种类0为矩形，三角形为1
        location为顶点坐标，逆时针顺序。
        :return:Xc,Yc分别为形心的横坐标和纵坐标
        '''
        # 三角形
        if gender == 1:
            Xc = (location[0][0] + location[1][0] + location[2][0]) / 3  # 利用重心的形心
            Yc = (location[0][1] + location[1][1] + location[2][1]) / 3

            y_max = max(location[0][1], location[1][1], location[2][1])
        # 矩形
        else:
            # 形心的横坐标  Xc=(x0+x1+...)/4
            Xc = 1 / 4 * (location[0][0] + location[1][0] + location[2][0] + location[3][0])
            # 形心的纵坐标  Yc=(y1+y2+...)/4
            Yc = 1 / 4 * (location[0][1] + location[1][1] + location[2][1] + location[3][1])
            y_max = max(location[0][1], location[1][1], location[2][1], location[3][1])
        Xc = round(Xc, self.numScale)
        Yc = round(Yc, self.numScale)
        return Xc, Yc, y_max

    def getThisArea(self, graph):
        '''
        得到多边形的 面积
        :param graph: 必须时封闭且按顺时针或逆时针排序:[[], [], [], [].....]
        :return:
        '''
        S = 0  # 面积

        point0 = graph[0]  # 随便取的一个基点，以该点划分除三角行
        for i in range(1, len(graph) - 1):
            point1 = graph[i]
            point2 = graph[i + 1]
            v1 = [point1[0] - point0[0], point1[1] - point0[1]]
            v2 = [point2[0] - point0[0], point2[1] - point0[1]]

            s = abs(v1[0] * v2[1] - v1[1] * v2[0]) / 2  # 一块小三角形的面积
            S = S + s

        return S

    def judgePointInner(self, x, y, location):
        '''
        判断点在多边形内, T在里面,在外面或在边上F
        进行区域规整的快速判断
        :param x: 判断点x
        :param y: 判断点y
        :param location:待检测区域。必须是按照边的顺序，连着给的点; 图形坐标:[[], [], [], []]
        :return:
        '''
        # 若点在规整区域外则直接返回F
        x_set = [i[0] for i in location]
        y_set = [i[1] for i in location]
        x_min = min(x_set)
        x_max = max(x_set)
        y_min = min(y_set)
        y_max = max(y_set)
        if x < x_min or x > x_max:
            return 1  # 在外面
        if y < y_min or y > y_max:
            return 1  # 在外面

        flag = -1  # -1在里面；0在边上；1在外面
        for i in range(len(location)):
            point = location[i]
            if i == 0:
                point_next = location[i + 1]
                point_bef = location[-1]
            elif i == len(location) - 1:
                point_next = location[0]
                point_bef = location[i - 1]
            else:
                point_next = location[i + 1]
                point_bef = location[i - 1]
            v0 = [x - point[0], y - point[1]]
            v1 = [point_next[0] - point[0], point_next[1] - point[1]]
            v2 = [point_bef[0] - point[0], point_bef[1] - point[1]]

            # 叉乘之积
            answer = (v0[0] * v1[1] - v1[0] * v0[1]) * (v0[0] * v2[1] - v2[0] * v0[1])
            if answer > 0:  # 在外面或在边上
                flag = 1
                return flag
            if answer == 0:
                flag = 0

        return flag  # 在里面

    # 重叠检测，出界检测
    def judgeCoin(self, Xc, Yc, location):
        '''
        待排图形与已排图形的重叠检测
        根据已排图形来

        location:待检查图形, [[], [], []]
        Xc:形心x
        Yc:形心y
        :return:    重叠T/不重叠F
        '''

        # 判断是否出界
        for point in location:
            x = point[0]
            y = point[1]
            if (x < 0) or (x > self.gridX):
                return True  # 出现出界
            if (y < 0) or (y > self.gridY):
                return True  # 出现出界

        # 最开始的情况
        if not self.settledPoints:
            return False

        x_list = [i[0] for i in location]
        y_list = [i[1] for i in location]
        x_min = min(x_list)  # 带派图形的x最低值
        x_max = max(x_list)
        y_min = min(y_list)
        y_max = max(y_list)

        # 遍历已经排放图形的顶点信息
        for Point in self.settledPoints:  # [[Yc, y_max, Xc, gender, location, num, s], ..]
            settledGraph = Point[4]  # [[], [], [], []] # 以排图形
            x_list_set = [i[0] for i in settledGraph]
            y_list_set = [i[1] for i in settledGraph]
            x_min_set = min(x_list_set)  # 已派图形的x最低值
            x_max_set = max(x_list_set)
            y_min_set = min(y_list_set)
            y_max_set = max(y_list_set)
            # 离得太远的直接跳过
            if x_max < x_min_set or x_min > x_max_set or y_max < y_min_set or y_min > y_max_set:
                continue

            # 检查形心
            exist0 = self.judgePointInner(Xc, Yc, settledGraph)
            if exist0 == -1 or exist0 == 0:  # 形心不能在里面或边上
                return True  # 形心在里面

            # 检查点在图形内
            for i in range(len(location)):
                x = location[i][0]
                y = location[i][1]
                exist1 = self.judgePointInner(x, y, settledGraph)  # 图形的顶点
                if exist1 == -1:  # 顶点可以在边上但不能在里面
                    return True  # 形心在里面

            # 检查边界线香蕉
            line_already = []  # 已排图形的线
            if len(settledGraph) == 3:  # 三角形
                l = [[settledGraph[0], settledGraph[1]],  # 边线1
                     [settledGraph[1], settledGraph[2]],  # 边线2
                     [settledGraph[2], settledGraph[0]],  # 边线3
                     # [settledGraph[0], [(settledGraph[1][0] + settledGraph[2][0])/2, (settledGraph[1][1] + settledGraph[2][1])/2]] ,   # 中线1
                     # [settledGraph[1], [(settledGraph[0][0] + settledGraph[2][0])/2, (settledGraph[0][1] + settledGraph[2][1])/2]]      # 中线2
                     ]
                line_already.extend(l)
            else:  # 矩形
                l = [[settledGraph[0], settledGraph[1]],  # 边线1
                     [settledGraph[1], settledGraph[2]],  # 边线2
                     [settledGraph[2], settledGraph[3]],  # 边线3
                     [settledGraph[3], settledGraph[0]],  # 边线4
                     # [settledGraph[0], settledGraph[2]],  # 中线1
                     # [settledGraph[1], settledGraph[3]]  # 中线2
                     ]
                line_already.extend(l)
            line_noready = []  # 未排图形的线
            if len(location) == 3:
                l = [[location[0], location[1]],  # 边线1
                     [location[1], location[2]],  # 边线2
                     [location[2], location[0]],  # 边线3
                     [location[0], [(location[1][0] + location[2][0]) / 2, (location[1][1] + location[2][1]) / 2]],
                     # 中线1
                     [location[1], [(location[0][0] + location[2][0]) / 2, (location[0][1] + location[2][1]) / 2]]
                     # 中线2
                     ]
                line_noready.extend(l)
            else:  # 矩形
                l = [[location[0], location[1]],  # 边线1
                     [location[1], location[2]],  # 边线2
                     [location[2], location[3]],  # 边线3
                     [location[3], location[0]],  # 边线4
                     [location[0], location[2]],  # 中线1
                     [location[1], location[3]]  # 中线2
                     ]
                line_noready.extend(l)

            for line0 in line_already:
                for line1 in line_noready:
                    exist = self.judgeLineCross(line1, line0)  # 检查线段
                    if exist:
                        return True  # 出现香蕉

        return False  # 检查中没有发现重叠的情况

    # 使用shapely
    # def judgeCoin_(self, location):
    #     # 判断是否出界
    #     for point in location:
    #         x = point[0]
    #         y = point[1]
    #         if (x < 0) or (x > self.gridX):
    #             return True # 出现出界
    #         if (y < 0) or (y > self.gridY):
    #             return True # 出现出界
    #
    #     # 最开始的情况
    #     if not self.settledPoints:
    #         return False
    #
    #     polygon0 = Polygon(location)
    #
    #     # 遍历已经排放图形的顶点信息
    #     for settledPoint in self.settledPoints:  # [[s, num, gender, [[], [], [], []]], ..]
    #         points = settledPoint[3]  # [[], [], [], []]
    #         polygon1 = Polygon(points)
    #         k = polygon1.disjoint(polygon0)    # 不重叠T/重叠F
    #         if not k:
    #             return True # 出现香蕉
    #     return False

    def refreshGrid(self, gender, location, delMode=False):
        '''
        刷新排样点
        将self.grid置1
        :location:需要刷新排样点的区域:[[], [], [], [], [], []...] 需要时按几何顺序排序且封闭
        :return:
        '''
        gridScale = self.gridScale

        if not delMode:
            for ycoor in range(int(self.gridY * gridScale) + 1):
                for xcoor in range(int(self.gridX * gridScale) + 1):
                    y = ycoor / gridScale
                    x = xcoor / gridScale
                    exist = self.judgePointInner(x, y, location)
                    if exist == 1:  # 点在外面
                        continue
                    elif exist == 0:  # 在边上
                        self.grids[xcoor, ycoor] = self.grids[xcoor, ycoor] + 0.5
                    else:  # 在里面
                        self.grids[xcoor, ycoor] = 1

                    for point in location:
                        self.grids[int(point[0]) * gridScale, int(point[1]) * gridScale] = 0.5
        else:
            for ycoor in range(int(self.gridY * gridScale) + 1):
                for xcoor in range(int(self.gridX * gridScale) + 1):
                    y = ycoor / gridScale
                    x = xcoor / gridScale

                    exist = self.judgePointInner(x, y, location)

                    if exist == 1:  # 点在外面
                        continue
                    elif exist == 0:  # 在边上
                        self.grids[xcoor, ycoor] = self.grids[xcoor, ycoor] - 0.5
                    else:  # 在里面
                        self.grids[xcoor, ycoor] = 0

                    for point in location:
                        self.grids[int(point[0]) * gridScale, int(point[1]) * gridScale] = 0.5

    def refreshData(self, chosenOne, save=False, delMode=False):
        '''
        刷新正在排样的图形
        :param chosenOne: [Yc, y_max, Xc, gender, location, num, s]
        :param notSave: 正常刷新，来下一个图形就把上衣个删除
        :param addFlag: 添加模式/删除模式
        :return:
        '''
        #print("refreshData")
        try:
            # 获取互斥锁后，进程只能在释放锁后下个进程才能进来
            self.mutex.acquire()

            # 更新optpoints
            k = [chosenOne[6], chosenOne[5], chosenOne[3], chosenOne[4]]
            if not delMode:
                try:
                    self.optpoints.remove(self.pastPoint)
                    self.optpoints.append(k)  # optpoint:[[s, num, gender, [[], [], [], []]], ..]
                except Exception:
                    self.optpoints.append(k)  # optpoint:[[s, num, gender, [[], [], [], []]], ..]

                if not save:
                    self.pastPoint = k
                else:
                    self.pastPoint = []
            else:
                self.optpoints.remove(k)

            # 互斥锁必须被释放掉
            self.mutex.release()
        except Exception as e:
            print("refreshData error: ", e)

    def pause(self):
        self.__flag.clear()

    def resume(self):
        self.__flag.set()

    def saveData(self, chosenOne, delMode=False):
        '''
        将拍好的图形保存, 同时关闭在图形内部的栅格
        :param chosenOne: [Yc, y_max, Xc, gender, location, num, s]
        :param location:
        :return:
        '''
        try:
            location = chosenOne[4]
            num = chosenOne[5]
            gender = chosenOne[3]

            y_max = max(location, key=lambda x: x[1])
            if not delMode:
                # 保存图形
                self.settledPoints.append(chosenOne)  # settledPoints:[[Yc, y_max, Xc, gender, location, num, s], ..]
                # 保存最高线
                self.y_list.append([y_max[1], num])  # y_max列表：[[y_max, num], [], []..]
                # 刷新栅格
                self.refreshGrid(gender, location)
            else:
                # 删除图形
                self.settledPoints.remove(chosenOne)
                # 删除最高线
                self.y_list.remove([y_max[1], num])

                self.refreshGrid(gender, location, delMode=True)

            self.y_list.sort(reverse=True)
            return self.y_list[0][0]  # 返回y_max
        except Exception as e:
            print("saveData error: ", e)

    def sortData(self, graphs):
        '''
        将self.iptpoint 的点按逆时针排列,并且图形左下角的点排第一个
        :graphs:原始数据信息：[[0, [[], [], [], []]], []...]
        :return:
        '''
        new_graph = []

        for graph in graphs:
            num = graph[0]
            gender = graph[1]  # 0/1
            location = graph[2]  # [[], [], [], []...]

            x_arr = [i[0] for i in location]
            y_arr = [i[1] for i in location]
            if gender == 0:  # 矩形
                x_min = min(x_arr)
                x_max = max(x_arr)
                y_min = min(y_arr)
                y_max = max(y_arr)
                new_graph.append([num, gender, [[x_min, y_min], [x_max, y_min], [x_max, y_max], [x_min, y_max]]])
            else:  # 三角形不做规整直接返回
                new_graph.append(copy.deepcopy(graph))
        return new_graph

    # 上传（刷新）数据
    def uploadData(self):
        #print("uploadData")
        try:
            # 获取互斥锁后，进程只能在释放锁后下个进程才能进来
            self.mutex.acquire()

            optpoints_data, stop = copy.deepcopy(self.optpoints), self.finishFlag

            # 互斥锁必须被释放掉
            self.mutex.release()

            return optpoints_data, stop
        except Exception as e:
            print("uploadData error: ", e)

    def downloadPossibleRects(self, possible_rects, best_rects, keyMap):
        try:
            self.possible_rects = possible_rects
            self.best_rects = best_rects
            self.keyMap = keyMap
            # self.possible_rects = copy.deepcopy(possible_rects)
            # self.best_rects = copy.deepcopy(best_rects)
            # self.keyMap = copy.deepcopy(keyMap)
        except Exception as e:
            print("downloadPossibleRects error:", e)

    # 采用self.possibleRects的第idx个模块组合方案
    def initNewIptpoints(self, try_idx):
        try:
            print("total = ", len(self.possible_rects), ", idx = ", try_idx, ", remain area = ", self.gridX*self.gridY - self.possible_rects[try_idx][0])

            new_iptpoints = []
            for v in self.possible_rects[try_idx][1]:
                gender = 0
                num = v[1]
                width = v[2]
                height = v[3]
                dumped_location = [[0, 0], [width, 0], [width, height], [0, height]]
                new_iptpoints.append([num, gender, dumped_location])  # [[0, [[], [], [], []]], []]
                if 'D' in self.keyMap[num]:
                    self.setRoom(num)
            # 传入新数据
            self.downloadData(new_iptpoints)
        except Exception as e:
            print("initNewIptpoints error:", e)

    # 下载数据，入口函数
    def downloadData(self, iptpoints):

        self.stopFlag = False  # 将上次清除画布用的退出标志还原
        self.finishFlag = False

        # 数据一次规整：完整矩形并按逆时针排序    [[num, gender, [[], [], [], []]], ..]
        dumpedData = self.sortData(iptpoints)

        # 栅格初始化
        self.initGrid()

        # 数据二次规整：添加面积并且保存到本地    [[s, num, gender, [[], [], [], []]], ..]
        S = 0  # 总面积
        for graph in dumpedData:
            num = graph[0]  # 图形标号
            gender = graph[1]  # 图形性别
            location = graph[2]  # 图形坐标
            s = self.getThisArea(location)  # 图形面积
            S += s
            self.iptpoints.append([s, num, gender, location])

            if gender == 0:
                self.rects.append([s, num, gender, location])
            else:
                self.tris.append([s, num, gender, location])

        for tri in self.tris:  # [[s, num, gender, [[], [], [], []]], ..]
            graph = tri[3]
            vec0 = [graph[1][0] - graph[0][0], graph[1][1] - graph[0][1]]
            vec1 = [graph[2][0] - graph[1][0], graph[2][1] - graph[1][1]]
            vec2 = [graph[0][0] - graph[2][0], graph[0][1] - graph[2][1]]

            a = vec0[0] * vec1[0] - vec0[1] * vec1[1]  # 为0则垂直
            b = vec0[0] * vec2[0] - vec0[1] * vec2[1]
            c = vec1[0] * vec2[0] - vec1[1] * vec2[1]

            if not a or not b or not c:
                self.virticalTris.append(tri)
            else:
                continue

        self.y_full = S / self.gridX  # 标准警戒线  # 1.138*S

        # 按面积由大到小排
        self.iptpoints.sort(reverse=True)
        self.tris.sort(reverse=True)
        #self.rects.sort(reverse=True)

        #print('下载完成', self.iptpoints)
        self.__globalFlag.set()  # 释放计算器

        return self.y_full  # 返回警戒线

    def clear(self):
        # 数据重置
        self.stopFlag = True
        self.iptpoints.clear()

        # 获取互斥锁后，进程只能在释放锁后下个进程才能进来
        self.mutex.acquire()
        self.optpoints = [[0, 0, -1, [[0, 0], [0, 0], [0, 0]]]]
        # 互斥锁必须被释放掉
        self.mutex.release()

        self.y_list.clear()
        self.tris.clear()
        self.rects.clear()
        self.grids = np
        self.settledPoints.clear()

        self.__globalFlag.clear()  # 锁定计算器
        self.resume()

    def run(self):

        while self.__running.isSet():
            self.__globalFlag.wait()
            # 开始计算
            start_time = time.time()
            answer = self.calculating()
            if answer:
                print('计算完成')
            else:
                print('计算终止')

            end_time = time.time()
            k = time.localtime(end_time - start_time)
            print('用时:' + str(time.strftime('%M:%S', k)))

            self.finishFlag = True
            self.__globalFlag.clear()  # 锁定计算器
            print('~~~~~~~~~~over~~~~~~~~~~~')



