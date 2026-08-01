from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget


ONE_TIME_BOOST_SESSIONS = 100
PERSISTENT_HIGH_SESSIONS = 32


def choose_concurrency_boost_mode(
    parent: QWidget,
    account_count: int,
    *,
    existing_fixed_high: bool = False,
) -> str | None:
    one_time_total = ONE_TIME_BOOST_SESSIONS * account_count
    persistent_total = PERSISTENT_HIGH_SESSIONS * account_count
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Warning)
    msg.setWindowTitle("加速执行")
    if account_count == 1:
        msg.setText(
            "请选择本次加速。"
            if existing_fixed_high
            else "请选择本次加速或持续固定并发。"
        )
        warning = (
            "仅本次加速：本次任务强制使用每房间 100 线程，停止后恢复原设置。\n"
            "线程过多可能触发 B 站风控，导致观看进度不计时。\n"
            + (
                "当前已经是固定 32 线程或更高；想要长期使用更多线程，"
                "请到高级设置中修改。"
                if existing_fixed_high
                else (
                    "持续高并发：把软件模式保存为固定 32 线程；"
                    "之后可在高级设置中手动修改。"
                )
            )
        )
    else:
        msg.setText(f"即将同时调整 {account_count} 个账号。")
        warning = (
            f"仅本次加速：100 × {account_count} = {one_time_total}。\n"
            + (
                "所选账号中已有固定 32 线程或更高设置；"
                "长期线程数请到高级设置中修改，本操作不会覆盖为 32。\n"
                if existing_fixed_high
                else (
                    f"持续高并发：32 × {account_count} = {persistent_total}，"
                    "并保存为固定 32。\n"
                )
            )
            + "高并发更容易触发 B 站风控，可能导致观看进度完全不计时。\n"
            "这里按每个账号一个房间计算；填写多个房间时实际连接数还会更高。"
        )
    msg.setInformativeText(warning)
    once_button = msg.addButton(
        "仅本次加速（100）",
        QMessageBox.ActionRole,
    )
    persistent_button = None
    if not existing_fixed_high:
        persistent_button = msg.addButton(
            "持续固定 32",
            QMessageBox.AcceptRole,
        )
    msg.addButton("取消", QMessageBox.RejectRole)
    msg.exec()
    clicked = msg.clickedButton()
    if clicked is once_button:
        return "once"
    if persistent_button is not None and clicked is persistent_button:
        return "persistent"
    return None
