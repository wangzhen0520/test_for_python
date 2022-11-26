# coding=utf-8
import wx
from PIL import Image


class Myframe(wx.Frame):
    def __init__(self, filename):
        wx.Frame.__init__(self, None, -1, u'图片显示', size=(640, 640))
        self.filename = filename
        self.Bind(wx.EVT_SIZE, self.change)
        self.p = wx.Panel(self, -1)
        self.SetBackgroundColour('white')

    def start(self):
        self.p.DestroyChildren()  # 抹掉原先显示的图片
        self.width, self.height = self.GetSize()
        print(self.width, self.height)

        # image = Image.open(self.filename)
        # self.x, self.y = image.size
        # self.x = self.width / 2 - self.x / 2
        # self.y = self.height / 2 - self.y / 2
        # img = wx.Image(self.filename, wx.BITMAP_TYPE_ANY)
        # # img = img.Scale(self.width, self.height)
        # self.pic = img.ConvertToBitmap()
        # # 通过计算获得图片的存放位置
        # print(self.x, self.y)

        image = wx.Image(self.filename, wx.BITMAP_TYPE_JPEG)
        self.x = 10
        self.y = 10
        self.pic = image.Scale(self.width, self.height).ConvertToBitmap()
        self.SetSize([self.width, self.height])
        self.button = wx.BitmapButton(self.p, -1, self.pic, pos=(self.x, self.y))
        self.p.Fit()

    def change(self, size):  # 如果检测到框架大小的变化，及时改变图片的位置
        if self.filename != "":
            self.start()
        else:
            pass


def main():
    app = wx.App()
    frame = Myframe('1.jpg')
    frame.start()
    frame.Center()
    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    main()
