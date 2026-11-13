import sys
import json
import uuid
import os
from enum import Enum
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QFont, QPainterPath, QKeySequence, 
    QShortcut, QImage, QPixmap
)
from PyQt6.QtWidgets import (
    QApplication, QGraphicsView, QGraphicsScene, QGraphicsTextItem,
    QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem, QMainWindow, 
    QToolBar, QButtonGroup, QRadioButton, QFileDialog, QPushButton, QColorDialog
)

class Mode(Enum):
    SELECT = 0
    PEN = 1
    TEXT = 2
    LINK = 3


# === ИЗОБРАЖЕНИЕ НА ХОЛСТЕ ===
class ImageCardItem(QGraphicsPixmapItem):
    def __init__(self, pixmap, image_path="", parent=None):
        super().__init__(pixmap, parent)
        self.image_path = image_path
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )

    def to_dict(self):
        return {
            "image_path": self.image_path,
            "x": self.x(),
            "y": self.y()
        }


# === РИСУНОК ПЕРОМ ===
class DrawingPathItem(QGraphicsPathItem):
    def __init__(self, path=None, points=None, color="#f38ba8", width=3, parent=None):
        super().__init__(parent)
        self.points = points if points is not None else []
        self.color_hex = color
        self.pen_width = width
        
        pen = QPen(QColor(self.color_hex), self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)
        
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | 
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        if path:
            self.setPath(path)

    def add_point(self, point: QPointF):
        self.points.append([point.x(), point.y()])

    def to_dict(self):
        return {
            "points": self.points,
            "color": self.color_hex,
            "width": self.pen_width,
            "x": self.x(),
            "y": self.y()
        }


# === СОЕДИНИТЕЛЬНАЯ ЛИНИЯ/СВЯЗЬ (КРИВАЯ БЕЗЬЕ) ===
class ConnectionItem(QGraphicsPathItem):
    def __init__(self, start_item, end_item, parent=None):
        super().__init__(parent)
        self.start_item = start_item
        self.end_item = end_item
        
        pen = QPen(QColor("#a6e3a1"), 2, Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
        
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        
        self.start_item.add_connection(self)
        self.end_item.add_connection(self)
        self.update_position()

    def update_position(self):
        if not self.start_item or not self.end_item:
            return
            
        p1 = self.start_item.sceneBoundingRect().center()
        p2 = self.end_item.sceneBoundingRect().center()
        
        path = QPainterPath()
        path.moveTo(p1)
        
        dx = p2.x() - p1.x()
        ctrl1 = QPointF(p1.x() + dx / 2, p1.y())
        ctrl2 = QPointF(p1.x() + dx / 2, p2.y())
        
        path.cubicTo(ctrl1, ctrl2, p2)
        self.setPath(path)

    def paint(self, painter, option, widget):
        if self.isSelected():
            pen = QPen(QColor("#f9e2af"), 3, Qt.PenStyle.DashLine)
            painter.setPen(pen)
        else:
            painter.setPen(self.pen())
            
        painter.drawPath(self.path())

    def remove_self(self):
        if self.start_item:
            self.start_item.remove_connection(self)
        if self.end_item:
            self.end_item.remove_connection(self)
        if self.scene():
            self.scene().removeItem(self)

    def to_dict(self):
        return {
            "start_id": self.start_item.id,
            "end_id": self.end_item.id
        }


# === ТЕКСТОВАЯ КАРТОЧКА ===
class TextCardItem(QGraphicsTextItem):
    def __init__(self, text="Новая заметка...", grid_size=30, item_id=None, parent=None):
        super().__init__(text, parent)
        self.id = item_id if item_id else str(uuid.uuid4())
        self.grid_size = grid_size
        self.connections = []
        
        self.setDefaultTextColor(QColor("#cdd6f4"))
        self.setFont(QFont("JetBrains Mono", 11))
        
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges |
            QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )

    def add_connection(self, connection):
        if connection not in self.connections:
            self.connections.append(connection)

    def remove_connection(self, connection):
        if connection in self.connections:
            self.connections.remove(connection)

    def mouseDoubleClickEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus()
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        super().focusOutEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos = value
            x = round(new_pos.x() / self.grid_size) * self.grid_size
            y = round(new_pos.y() / self.grid_size) * self.grid_size
            return QPointF(x, y)

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            for conn in self.connections:
                conn.update_position()

        return super().itemChange(change, value)

    def paint(self, painter, option, widget):
        rect = self.boundingRect().adjusted(-8, -4, 8, 4)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        painter.setBrush(QColor("#313244"))
        border_pen = QPen(QColor("#89b4fa"), 2) if self.isSelected() else QPen(QColor("#45475a"), 1)
        painter.setPen(border_pen)
        painter.drawRoundedRect(rect, 8, 8)
        
        super().paint(painter, option, widget)

    def to_dict(self):
        return {
            "id": self.id,
            "text": self.toPlainText(),
            "x": self.x(),
            "y": self.y()
        }


# === БЕСКОНЕЧНЫЙ ХОЛСТ ===
class SpatialCanvasView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.grid_size = 30
        self.mode = Mode.SELECT
        self.current_pen_color = "#f38ba8"
        self.current_pen_width = 3
        
        self._is_panning = False
        self._pan_start = QPointF()
        
        self._current_drawing_item = None
        self._link_start_card = None
        self._temp_line_item = None

    def set_mode(self, mode: Mode):
        self.mode = mode
        if mode == Mode.PEN:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif mode == Mode.TEXT:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        elif mode == Mode.LINK:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def keyPressEvent(self, event):
        focus_item = self.scene().focusItem()
        if isinstance(focus_item, QGraphicsTextItem) and (focus_item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction):
            super().keyPressEvent(event)
            return

        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            for item in list(self.scene().selectedItems()):
                if isinstance(item, TextCardItem):
                    for conn in list(item.connections):
                        conn.remove_self()
                    self.scene().removeItem(item)
                elif isinstance(item, ConnectionItem):
                    item.remove_self()
                else:
                    self.scene().removeItem(item)
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(zoom_factor, zoom_factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton or (event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.AltModifier):
            self._is_panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        scene_pos = self.mapToScene(event.position().toPoint())

        if self.mode == Mode.PEN and event.button() == Qt.MouseButton.LeftButton:
            path = QPainterPath(scene_pos)
            self._current_drawing_item = DrawingPathItem(
                path=path, 
                color=self.current_pen_color, 
                width=self.current_pen_width
            )
            self._current_drawing_item.add_point(scene_pos)
            self.scene().addItem(self._current_drawing_item)
            return

        if self.mode == Mode.TEXT and event.button() == Qt.MouseButton.LeftButton:
            existing_item = self.scene().itemAt(scene_pos, self.transform())
            if existing_item is not None:
                super().mousePressEvent(event)
                return

            gx = round(scene_pos.x() / self.grid_size) * self.grid_size
            gy = round(scene_pos.y() / self.grid_size) * self.grid_size
            
            card = TextCardItem(grid_size=self.grid_size)
            card.setPos(gx, gy)
            self.scene().addItem(card)
            
            card.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            card.setFocus()
            return

        if self.mode == Mode.LINK and event.button() == Qt.MouseButton.LeftButton:
            clicked_item = self.scene().itemAt(scene_pos, self.transform())
            if isinstance(clicked_item, TextCardItem):
                self._link_start_card = clicked_item
                
                path = QPainterPath(clicked_item.sceneBoundingRect().center())
                path.lineTo(scene_pos)
                pen = QPen(QColor("#a6e3a1"), 2, Qt.PenStyle.DashLine)
                self._temp_line_item = self.scene().addPath(path, pen)
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())

        if self._is_panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - delta.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - delta.y()))
            return

        if self.mode == Mode.PEN and self._current_drawing_item and (event.buttons() & Qt.MouseButton.LeftButton):
            path = self._current_drawing_item.path()
            path.lineTo(scene_pos)
            self._current_drawing_item.setPath(path)
            self._current_drawing_item.add_point(scene_pos)
            return

        if self.mode == Mode.LINK and self._link_start_card and self._temp_line_item:
            path = QPainterPath(self._link_start_card.sceneBoundingRect().center())
            path.lineTo(scene_pos)
            self._temp_line_item.setPath(path)
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())

        if self._is_panning:
            self._is_panning = False
            self.set_mode(self.mode)
            return

        if self.mode == Mode.PEN and event.button() == Qt.MouseButton.LeftButton:
            self._current_drawing_item = None
            return

        if self.mode == Mode.LINK and event.button() == Qt.MouseButton.LeftButton:
            if self._temp_line_item:
                self.scene().removeItem(self._temp_line_item)
                self._temp_line_item = None

            if self._link_start_card:
                target_item = self.scene().itemAt(scene_pos, self.transform())
                if isinstance(target_item, TextCardItem) and target_item != self._link_start_card:
                    connection = ConnectionItem(self._link_start_card, target_item)
                    self.scene().addItem(connection)

                self._link_start_card = None
            return

        super().mouseReleaseEvent(event)

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor("#1e1e2e"))
        pen = QPen(QColor("#45475a"))
        pen.setWidth(2)
        painter.setPen(pen)

        left = int(rect.left()) - (int(rect.left()) % self.grid_size)
        top = int(rect.top()) - (int(rect.top()) % self.grid_size)

        for x in range(left, int(rect.right()), self.grid_size):
            for y in range(top, int(rect.bottom()), self.grid_size):
                painter.drawPoint(x, y)

    # === СОХРАНЕНИЕ ===
    def save_to_file(self, filename):
        cards_data = []
        drawings_data = []
        connections_data = []
        images_data = []

        for item in self.scene().items():
            if isinstance(item, TextCardItem):
                cards_data.append(item.to_dict())
            elif isinstance(item, DrawingPathItem):
                drawings_data.append(item.to_dict())
            elif isinstance(item, ConnectionItem):
                connections_data.append(item.to_dict())
            elif isinstance(item, ImageCardItem):
                images_data.append(item.to_dict())

        data = {
            "cards": cards_data,
            "drawings": drawings_data,
            "connections": connections_data,
            "images": images_data
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # === ЗАГРУЗКА ===
    def load_from_file(self, filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки файла: {e}")
            return

        self.scene().clear()
        card_map = {}

        for c_data in data.get("cards", []):
            card = TextCardItem(text=c_data.get("text", ""), grid_size=self.grid_size, item_id=c_data.get("id"))
            card.setPos(c_data.get("x", 0), c_data.get("y", 0))
            self.scene().addItem(card)
            card_map[card.id] = card

        for d_data in data.get("drawings", []):
            points = d_data.get("points", [])
            if not points:
                continue

            path = QPainterPath(QPointF(points[0][0], points[0][1]))
            for pt in points[1:]:
                path.lineTo(QPointF(pt[0], pt[1]))

            drawing = DrawingPathItem(
                path=path,
                points=points,
                color=d_data.get("color", "#f38ba8"),
                width=d_data.get("width", 3)
            )
            drawing.setPos(d_data.get("x", 0), d_data.get("y", 0))
            self.scene().addItem(drawing)

        for conn_data in data.get("connections", []):
            start_card = card_map.get(conn_data.get("start_id"))
            end_card = card_map.get(conn_data.get("end_id"))

            if start_card and end_card:
                connection = ConnectionItem(start_card, end_card)
                self.scene().addItem(connection)
                connection.update_position()

        for img_data in data.get("images", []):
            path = img_data.get("image_path", "")
            if os.path.exists(path):
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    img_item = ImageCardItem(pixmap, image_path=path)
                    img_item.setPos(img_data.get("x", 0), img_data.get("y", 0))
                    self.scene().addItem(img_item)

    # === ЭКСПОРТ В PNG ===
    def export_to_image(self, filename):
        items = self.scene().items()
        if not items:
            print("Холст пуст, нечего экспортировать.")
            return

        rect = self.scene().itemsBoundingRect().adjusted(-40, -40, 40, 40)
        image = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_ARGB32)
        image.fill(QColor("#1e1e2e"))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.scene().render(painter, target=QRectF(image.rect()), source=rect)
        painter.end()

        image.save(filename)


# === ГЛАВНОЕ ОКНО ===
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spatial Canvas — Phase 5")
        self.resize(1300, 800)

        self.scene = QGraphicsScene(-50000, -50000, 100000, 100000)
        self.view = SpatialCanvasView(self.scene)
        self.setCentralWidget(self.view)

        self._setup_toolbar()
        self._setup_shortcuts()

    def _setup_toolbar(self):
        toolbar = QToolBar("Инструменты")
        toolbar.setStyleSheet("""
            QToolBar { background: #181825; border-bottom: 1px solid #313244; padding: 5px; spacing: 8px; }
            QRadioButton { color: #cdd6f4; font-weight: bold; padding: 5px 10px; border-radius: 4px; }
            QRadioButton::checked { background: #89b4fa; color: #11111b; }
            QRadioButton::indicator { width: 0px; height: 0px; }
            QPushButton { background: #313244; color: #cdd6f4; font-weight: bold; padding: 5px 10px; border-radius: 4px; border: 1px solid #45475a; }
            QPushButton:hover { background: #45475a; }
        """)
        self.addToolBar(toolbar)

        btn_group = QButtonGroup(self)

        rb_select = QRadioButton("🖐️ Выделение")
        rb_pen = QRadioButton("✏️ Перо")
        rb_text = QRadioButton("📝 Текст")
        rb_link = QRadioButton("🔗 Связь")

        rb_select.setChecked(True)

        btn_group.addButton(rb_select, Mode.SELECT.value)
        btn_group.addButton(rb_pen, Mode.PEN.value)
        btn_group.addButton(rb_text, Mode.TEXT.value)
        btn_group.addButton(rb_link, Mode.LINK.value)

        toolbar.addWidget(rb_select)
        toolbar.addWidget(rb_pen)
        toolbar.addWidget(rb_text)
        toolbar.addWidget(rb_link)

        toolbar.addSeparator()

        colors = [
            ("🌸", "#f38ba8"),
            ("🌿", "#a6e3a1"),
            ("💧", "#89b4fa"),
            ("⚡", "#f9e2af"),
            ("🤍", "#cdd6f4"),
        ]

        for icon, color_hex in colors:
            btn_color = QPushButton(icon)
            btn_color.setFixedWidth(32)
            btn_color.setToolTip(f"Цвет пера: {color_hex}")
            btn_color.clicked.connect(lambda _, c=color_hex: self.set_pen_color(c))
            toolbar.addWidget(btn_color)

        btn_picker = QPushButton("🎨 Цвет")
        btn_picker.clicked.connect(self.choose_custom_color)
        toolbar.addWidget(btn_picker)

        toolbar.addSeparator()

        btn_img = QPushButton("🖼️ Вставить фото")
        btn_save = QPushButton("💾 Сохранить")
        btn_load = QPushButton("📂 Открыть")
        btn_export = QPushButton("📤 Экспорт PNG")

        btn_img.clicked.connect(self.insert_image)
        btn_save.clicked.connect(self.save_canvas)
        btn_load.clicked.connect(self.load_canvas)
        btn_export.clicked.connect(self.export_png)

        toolbar.addWidget(btn_img)
        toolbar.addWidget(btn_save)
        toolbar.addWidget(btn_load)
        toolbar.addWidget(btn_export)

        btn_group.idToggled.connect(lambda mode_id, checked: self.view.set_mode(Mode(mode_id)) if checked else None)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+S"), self, self.save_canvas)
        QShortcut(QKeySequence("Ctrl+O"), self, self.load_canvas)
        QShortcut(QKeySequence("Ctrl+E"), self, self.export_png)
        QShortcut(QKeySequence("Ctrl+I"), self, self.insert_image)

    def set_pen_color(self, color_hex):
        self.view.current_pen_color = color_hex

    def choose_custom_color(self):
        color = QColorDialog.getColor(QColor(self.view.current_pen_color), self, "Выберите цвет пера")
        if color.isValid():
            self.view.current_pen_color = color.name()

    def insert_image(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, 
            "Выберите изображение", 
            "", 
            "Все файлы (*);;Изображения (*.png *.jpg *.jpeg *.bmp)"
        )
        if filepath:
            pixmap = QPixmap(filepath)
            if not pixmap.isNull():
                img_item = ImageCardItem(pixmap, image_path=filepath)
                center_pos = self.view.mapToScene(self.view.viewport().rect().center())
                img_item.setPos(center_pos)
                self.scene.addItem(img_item)

    def save_canvas(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, 
            "Сохранить холст", 
            "canvas.json", 
            "JSON Files (*.json)"
        )
        if filepath:
            if not filepath.endswith(".json"):
                filepath += ".json"
            self.view.save_to_file(filepath)

    def load_canvas(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, 
            "Открыть холст", 
            "", 
            "JSON Files (*.json);;Все файлы (*)"
        )
        if filepath:
            self.view.load_from_file(filepath)

    def export_png(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, 
            "Экспортировать холст в PNG", 
            "canvas.png", 
            "PNG Images (*.png)"
        )
        if filepath:
            if not filepath.endswith(".png"):
                filepath += ".png"
            self.view.export_to_image(filepath)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
