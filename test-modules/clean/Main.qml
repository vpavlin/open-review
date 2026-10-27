import QtQuick
Rectangle { color: "#111"
  Text { id: t; anchors.centerIn: parent; color: "#9fe"; font.pixelSize: 40 }
  Timer { interval: 1000; running: true; repeat: true; triggeredOnStart: true
    onTriggered: t.text = Qt.formatDateTime(new Date(), "hh:mm:ss") } }
