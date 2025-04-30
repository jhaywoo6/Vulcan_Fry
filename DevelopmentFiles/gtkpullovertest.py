import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

class MyWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="GTK Entry with Popover")
        self.set_default_size(300, 100)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(vbox)

        # Entry field
        self.entry = Gtk.Entry()
        vbox.pack_start(self.entry, False, False, 0)

        # Popover button
        button = Gtk.Button(label="▼")
        vbox.pack_start(button, False, False, 0)
        
        # Popover
        self.popover = Gtk.Popover()
        self.popover.set_relative_to(button)
        
        popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.popover.add(popover_box)
        
        options = ["Option 1", "Option 2", "Option 3"]
        for option in options:
            btn = Gtk.Button(label=option)
            btn.connect("clicked", self.on_option_selected)
            popover_box.pack_start(btn, False, False, 0)

        self.popover.show_all()
        button.connect("clicked", self.on_button_clicked)
    
    def on_button_clicked(self, widget):
        self.popover.show_all()
        self.popover.popup()
    
    def on_option_selected(self, button):
        self.entry.set_text(button.get_label())
        self.popover.popdown()

win = MyWindow()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()
