#!/usr/bin/env python2

from gi.repository import Gtk, Gio
import os
import re
import stat
import sys


class SpaceHoarderApp(Gtk.Application):
    COLORS_STRING = "fb4b2d, db6e2c, fb9928, f3c71c, a7c71c, 809921, " + \
        "86c1a1, 7241bc, c53aa9, ff3a90"
    COLORS = None
    FONT_SIZE = 8
    PAD = 1
    SORT = True

    def __init__(self):
        Gtk.Application.__init__(
            self,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        )
        self.file = None

    def do_activate(self):
        window = SpaceHoarderWindow(self)
        window.show_all()

    def do_command_line(self, args):
        Gtk.Application.do_command_line(self, args)
        l = args.get_arguments()[1:]
        if len(l) > 0:
            self.file = l[0]
        self.do_activate()
        return 0


# Alias for less typing of constants.
S = SpaceHoarderApp


class SpaceHoarderWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        Gtk.Window.__init__(self, title="SpaceHoarder", application=app)
        self.set_default_size(700, 450)

        openBtn = Gtk.Button(label="Open")
        openBtn.connect("clicked", self.onOpenClicked)

        self.pathLb = Gtk.Label(single_line_mode=True)
        self.pathLb.set_alignment(0, 0.5)

        hbox = Gtk.HBox(spacing=5)
        hbox.pack_start(openBtn, False, False, 0)
        hbox.pack_start(self.pathLb, True, True, 0)

        self.drawingArea = Gtk.DrawingArea()
        self.drawingArea.connect("draw", self.onDraw)

        vbox = Gtk.VBox()
        vbox.pack_start(hbox, False, False, 0)
        vbox.pack_start(self.drawingArea, True, True, 0)

        self.add(vbox)
        self.lastSize = (-1, -1)
        self.dirModel = None
        self.fileRects = None

        if app.file is not None:
            self.usePath(app.file)

    def onOpenClicked(self, button):
        action = Gtk.FileChooserAction.SELECT_FOLDER,
        opts = (
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.ACCEPT
        )
        dialog = Gtk.FileChooserDialog("Pick a directory", self, action, opts)
        dialog.set_local_only(False)
        dialog.set_modal(True)
        dialog.connect("response", self.onDirSelected)
        dialog.show()

    def onDirSelected(self, dialog, responseId):
        if responseId == Gtk.ResponseType.ACCEPT:
            self.usePath(dialog.get_filename())
        dialog.destroy()

    def onDraw(self, widget, cr):
        rect = self.drawingArea.get_allocation()
        size = rect.width, rect.height

        if self.dirModel is None:
            pass  # TODO: Draw an empty rectangle.
        else:
            if size != self.lastSize:
                self.lastSize = size
                self.fileRects = self.dirModel.getAllRects(size)

            self.drawFileRects(cr)

        return False

    def usePath(self, path):
        self.pathLb.set_label(path)
        self.dirModel = DirModel(path)
        self.fileRects = self.dirModel.getAllRects(self.lastSize)
        self.drawingArea.queue_draw()

    def drawFileRects(self, cr):
        cr.select_font_face("Sans")
        cr.set_font_size(S.FONT_SIZE)

        for f in self.fileRects:
            color = S.COLORS[f.colorIndex]
            cr.set_source_rgb(color[0], color[1], color[2])
            cr.rectangle(f.x, f.y, f.w, f.h)
            cr.fill()

            if min(f.w, f.h) > S.FONT_SIZE + 2 * S.PAD:
                cr.rectangle(f.x, f.y, f.w - S.PAD, f.h - S.PAD)
                cr.clip()
                cr.set_source_rgb(0, 0, 0)
                cr.move_to(f.x + S.PAD, f.y + S.FONT_SIZE + S.PAD)
                cr.show_text(f.name)
                cr.reset_clip()


class FileModel:
    def __init__(self, name, size, depth):
        self.name = name
        self.size = size
        self.depth = depth

    def getFileRect(self, x, y, w, h, isContainer):
        # If it's smaller than this it can't be drawn.
        if w <= S.PAD and h <= S.PAD:
            return None

        color = self.depth % len(S.COLORS)
        return FileRect(x, y, w, h, self.name, color, isContainer)

    def addFileRects(self, rects, x, y, w, h):
        rect = self.getFileRect(x, y, w, h, False)
        if rect is not None:
            rects.append(rect)


class DirModel(FileModel):
    def __init__(self, path, depth=0):
        FileModel.__init__(self, os.path.basename(path), 0, depth)
        self.contains = []
        self.size = 0

        try:
            dirs = os.listdir(path)
        except OSError:
            return

        for f in dirs:
            pathname = os.path.join(path, f)
            try:
                # The file might not exist anymore
                st = os.stat(pathname)
            except:
                continue
            mode = st.st_mode
            if stat.S_ISDIR(mode):
                newDir = DirModel(pathname, self.depth + 1)
                self.contains.append(newDir)
                self.size += newDir.size
            elif stat.S_ISREG(mode):
                fileSize = st.st_size
                newFile = FileModel(f, fileSize, self.depth + 1)
                self.contains.append(newFile)
                self.size += fileSize

        if S.SORT:
            self.contains = sorted(self.contains, key=lambda x: x.size)

    def addFileRects(self, rects, x, y, w, h):
        rect = self.getFileRect(x, y, w, h, True)
        if rect is not None:
            rects.append(rect)
            pd = S.PAD
            d = S.FONT_SIZE + 2 * pd
            self.addSplited(rects, self.contains, x+pd, y+d, w-2*pd, h-d-pd)

    def addSplited(self, rects, group, x, y, w, h):
        if len(group) == 0 or w <= S.PAD or h <= S.PAD:
            return
        if len(group) == 1:
            group[0].addFileRects(rects, x, y, w, h)
            return

        split = [[], []]
        total = [0, 0]
        which = 0

        for f in group:
            # Ignore empty files.
            if f.size == 0:
                continue

            split[which].append(f)
            total[which] += f.size

            if total[which] >= total[(which + 1) % 2]:
                which = (which + 1) % 2

        # Split according to which is bigger: the horizontal or the vertical.
        # TODO: Prefer splitting horizontally if rectangles are very small.
        ratio = total[0] / float(total[0] + total[1])
        dim = (w if w > h else h) - S.PAD
        p = int(ratio * dim)
        r = dim - p
        if w > h:
            self.addSplited(rects, split[0], x, y, p, h)
            self.addSplited(rects, split[1], x+w-r, y, r, h)
        else:
            self.addSplited(rects, split[0], x, y, w, p)
            self.addSplited(rects, split[1], x, y+h-r, w, r)

    def getAllRects(self, size):
        rects = []
        self.addFileRects(rects, 0, 0, size[0], size[1])
        return rects


class FileRect:
    def __init__(self, x, y, w, h, name, colorIndex, isContainer):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.name = name
        self.colorIndex = colorIndex
        self.isContainer = isContainer


def hex2tuple(h):
    n = int(h, 16)
    return (n >> 16) / 255.0, ((n >> 8) & 0xFF) / 255.0, (n & 0xFF) / 255.0


if __name__ == "__main__":
    hexColors = re.findall(r"[0-9a-fA-F]{6}", S.COLORS_STRING)
    S.COLORS = [hex2tuple(x) for x in hexColors]
    app = SpaceHoarderApp()
    exitStatus = app.run(sys.argv)
    sys.exit(exitStatus)
