import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import date, timedelta
from data_manager import DataManager, UserRole, TimeSlot

tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
dm = DataManager(data_dir=tmp)
dm.init_sample_data()

ins_002 = [i for i in dm.instruments if i.code == "INS-002"][0]
dm.freeze_instrument(ins_002.id, "手动测试用 - 光源不稳定，请更换", "张工", UserRole.ADMIN)
dm.unfreeze_instrument(ins_002.id, "光源已更换完成，测试通过", "李工", UserRole.ADMIN)

dm.settings.ins_filter_person = "张工"
dm.settings.ins_filter_status = "正常"
dm.settings.filter_person = "李工"
dm.settings.filter_status = "草稿"
dm.settings.export_dir = tmp
dm.save_settings()

print("准备完成：")
print(f"  已生成 1 次冻结 + 1 次解冻记录，可用于验证校准记录界面")
print(f"  仪器筛选 = 负责人'张工' + 状态'正常'")
print(f"  预约筛选 = 负责人'李工' + 状态'草稿'")
print(f"  现在可以启动 python app.py 验证跨重启恢复")
