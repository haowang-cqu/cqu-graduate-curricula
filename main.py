import requests
import re
from ics import Calendar, Event
from lxml import etree
from datetime import datetime, timedelta
from typing import List

USER_ID = ""                 # 学号
PASSWORD = ""                # 密码
TERM = 2                     # 学期 1 或者 2
START_TIME = "2023-02-13"    # 第一周周一的日期
LOGIN_URL = "http://mis.cqu.edu.cn/mis/login.jsp"
STUDENT_MANAGE_URL = "http://mis.cqu.edu.cn/mis/student_manage.jsp"
CURRICULA_URL = "http://mis.cqu.edu.cn/mis/curricula/show_stu.jsp"


def datetime_calc(week: int, week_day: int, interval: str):
    """根据周次和节次计算课程的开始和结束时间"""
    class_time = {
        "1-2": [timedelta(hours=8, minutes=30), timedelta(hours=10, minutes=10)],
        "3-4": [timedelta(hours=10, minutes=30), timedelta(hours=12, minutes=10)],
        "6-7": [timedelta(hours=14, minutes=25), timedelta(hours=16, minutes=5)],
        "8-9": [timedelta(hours=16, minutes=25), timedelta(hours=18, minutes=5)],
        "10-12": [timedelta(hours=19, minutes=0), timedelta(hours=21, minutes=35)]
    }
    start_time = datetime.strptime(START_TIME, "%Y-%m-%d")
    begin = start_time + timedelta(weeks=week - 1, days=week_day - 1) + class_time[interval][0]
    end = start_time + timedelta(weeks=week - 1, days=week_day - 1) + class_time[interval][1]
    # 转为GMT时间
    begin = begin - timedelta(hours=8)
    end = end - timedelta(hours=8)
    return (begin, end)


def login(user_id: str, password: str, user_type: str = "student", session = None):
    """登录并返回 stuSerial"""
    if not session:
        session = requests.session()
    session.post(LOGIN_URL, data={
        "userId": user_id,
        "password": password,
        "userType": user_type})
    resp = session.get(STUDENT_MANAGE_URL)
    if resp.status_code != 200:
        return None
    result = re.search(r"stuSerial=\d+", resp.text)
    if result:
        return result.group().split("=")[1]
    return None


def get_curricula(stu_serial: str, term: int = 1, session = None):
    """获取课表"""
    if not session:
        session = requests.session()
    resp = session.post(CURRICULA_URL, data={"stuSerial": stu_serial, "term": term})
    if resp.status_code != 200:
        return None
    return resp.text


def class_handler(class_description: List[str], week_day: int):
    """处理课程信息"""
    name = ""
    location = ""
    description = "\n".join(class_description)
    interval = ""
    weeks = []
    for i in class_description:
        if i.startswith("名称"):
            name = i.split("：")[1]
        if i.startswith("教室"):
            location = i.split("：")[1]
        if i.startswith("节次"):
            interval = i.split("：")[1]
        if i.startswith("周次"):
            temp = i.split("：")[1].strip("周").split()
            for j in temp:
                if "-" in j:
                    start, end = map(int, j.split("-"))
                    weeks += list(range(start, end + 1))
                else:
                    weeks.append(int(j))
    classes = []
    for week in weeks:
        begin, end = datetime_calc(week, week_day, interval)
        classes.append({
            "name": name,
            "location": location,
            "begin": begin,
            "end": end,
            "description": description
        })
    return classes

def split_class_description(content: List[str]):
    """根据班号分割课程"""
    class_descriptions = []
    start = 0
    for i in range(len(content)):
        if content[i].startswith("班号") and i != start:
            class_descriptions.append(content[start:i])
            start = i
        elif i == len(content) - 1:
            class_descriptions.append(content[start:])
    return class_descriptions


def parse_curricula(curricula: str):
    """解析课表"""
    html = etree.HTML(curricula)
    intervals = html.xpath("//tr")[2:]          # 5个时间段的课程数据
    classes = []
    for i in range(len(intervals)):
        days = intervals[i].xpath("td")[1:]         # 7天的课程数据
        for j in range(len(days)):
            content = days[j].xpath("text()")       # 课程内容, 里面可能存在多节课的信息
            if len(content) <= 1:
                continue
            # 根据班号分割课程
            for class_description in split_class_description(content):
                classes += class_handler(class_description, j + 1)
    return classes


def create_ics(classes):
    """生成ics文件"""
    cal = Calendar()
    for i in classes:
        event = Event(name=i["name"], begin=i["begin"], end=i["end"], location=i["location"], description=i["description"])
        cal.events.add(event)
    with open("curricula.ics", "w", encoding="utf-8") as f:
        f.writelines(cal.serialize_iter())


session = requests.session()
stu_serial = login(USER_ID, PASSWORD, session=session)
if not stu_serial:
    print("导出课程表失败，检查学号和密码是否正确")
    exit(-1)
classes = parse_curricula(get_curricula(stu_serial, term=2, session=session))
create_ics(classes)
print("导出课程表成功，文件名为curricula.ics")
