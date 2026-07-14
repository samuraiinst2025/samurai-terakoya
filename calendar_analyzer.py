#!/usr/bin/env python3
"""
iCloudカレンダー分析ツール
iCloudカレンダーから1週間の空き時間情報を取得してExcelで出力
"""

import sys
from datetime import datetime, timedelta
from typing import List, Tuple
import getpass

from caldav import DAVClient
from icalendar import Calendar
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Alignment, Border, Side
from dateutil import parser as date_parser


class CalendarAnalyzer:
    def __init__(self, email: str, password: str):
        """iCloudカレンダークライアントを初期化"""
        self.email = email
        self.password = password
        self.client = None
        self.principal = None

    def connect(self) -> bool:
        """iCloudに接続"""
        try:
            self.client = DAVClient(
                url='https://caldav.icloud.com/',
                username=self.email,
                password=self.password
            )
            self.principal = self.client.principal()
            print("✓ iCloudに接続しました")
            return True
        except Exception as e:
            print(f"✗ 接続エラー: {e}")
            print("注: iCloud 2段階認証の場合、パスワードの代わりにアプリパスワードを使用してください")
            return False

    def get_events_for_week(self, start_date: datetime) -> List[Tuple[str, datetime, datetime]]:
        """
        1週間のイベントを取得
        Returns: [(イベント名, 開始時刻, 終了時刻), ...]
        """
        events = []
        end_date = start_date + timedelta(days=7)

        try:
            calendars = self.principal.calendars()
            for calendar in calendars:
                try:
                    # イベントを日付範囲で検索
                    cal_events = calendar.search(
                        start=start_date,
                        end=end_date,
                        expand=True
                    )

                    for event in cal_events:
                        ical = event.icalendar_object

                        for component in ical.walk():
                            if component.name == "VEVENT":
                                summary = str(component.get('summary', '(未設定)'))
                                dtstart = component.get('dtstart')
                                dtend = component.get('dtend')

                                if dtstart and dtend:
                                    start = dtstart.dt
                                    end = dtend.dt

                                    # datetime型に統一
                                    if isinstance(start, datetime):
                                        events.append((summary, start, end))
                except Exception as e:
                    print(f"警告: カレンダー読み込みエラー: {e}")
                    continue
        except Exception as e:
            print(f"✗ イベント取得エラー: {e}")
            return []

        # 開始時刻でソート
        events.sort(key=lambda x: x[1])
        return events

    def calculate_free_time(
        self,
        events: List[Tuple[str, datetime, datetime]],
        start_date: datetime,
        work_start: int = 9,
        work_end: int = 18
    ) -> List[Tuple[datetime, datetime]]:
        """
        空き時間を計算
        Args:
            events: イベントリスト
            start_date: 対象週の開始日
            work_start: 業務開始時刻（デフォルト9時）
            work_end: 業務終了時刻（デフォルト18時）
        """
        free_slots = []

        for day_offset in range(7):
            current_day = start_date + timedelta(days=day_offset)
            day_start = current_day.replace(hour=work_start, minute=0, second=0)
            day_end = current_day.replace(hour=work_end, minute=0, second=0)

            # その日のイベントをフィルタ
            day_events = [
                (s, e) for name, s, e in events
                if s.date() == current_day.date()
            ]
            day_events.sort()

            current_time = day_start

            for event_start, event_end in day_events:
                # イベント前の空き時間
                if current_time < event_start:
                    free_slots.append((current_time, event_start))
                current_time = max(current_time, event_end)

            # 業務終了まで空き
            if current_time < day_end:
                free_slots.append((current_time, day_end))

        return free_slots

    def export_to_excel(
        self,
        events: List[Tuple[str, datetime, datetime]],
        free_slots: List[Tuple[datetime, datetime]],
        output_file: str = 'calendar_analysis.xlsx'
    ):
        """Excel形式で出力"""
        wb = Workbook()
        ws = wb.active
        ws.title = "カレンダー分析"

        # スタイル設定
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
        event_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        free_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # ヘッダー
        ws['A1'] = "予定分析結果"
        ws['A1'].font = ws['A1'].font.copy()
        ws['A1'].font = ws['A1'].font.copy()
        ws.row_dimensions[1].height = 25

        # 予定表
        ws['A3'] = "【予定一覧】"
        row = 4

        ws['A4'] = "開始"
        ws['B4'] = "終了"
        ws['C4'] = "タイトル"
        ws['D4'] = "時間"

        for col in ['A', 'B', 'C', 'D']:
            ws[f'{col}4'].fill = header_fill
            ws[f'{col}4'].border = border

        for title, start, end in events:
            ws[f'A{row}'] = start.strftime('%Y-%m-%d %H:%M')
            ws[f'B{row}'] = end.strftime('%Y-%m-%d %H:%M')
            ws[f'C{row}'] = title
            duration = (end - start).total_seconds() / 3600
            ws[f'D{row}'] = f"{duration:.1f}時間"

            for col in ['A', 'B', 'C', 'D']:
                ws[f'{col}{row}'].border = border
                ws[f'{col}{row}'].fill = event_fill
            row += 1

        # 空き時間表
        ws[f'A{row+2}'] = "【空き時間一覧】"
        row += 3

        ws[f'A{row}'] = "開始"
        ws[f'B{row}'] = "終了"
        ws[f'C{row}'] = "時間"
        ws[f'D{row}'] = "日付"

        for col in ['A', 'B', 'C', 'D']:
            ws[f'{col}{row}'].fill = header_fill
            ws[f'{col}{row}'].border = border

        row += 1
        for start, end in free_slots:
            ws[f'A{row}'] = start.strftime('%H:%M')
            ws[f'B{row}'] = end.strftime('%H:%M')
            duration = (end - start).total_seconds() / 3600
            ws[f'C{row}'] = f"{duration:.1f}時間"
            ws[f'D{row}'] = start.strftime('%Y-%m-%d (%a)')

            for col in ['A', 'B', 'C', 'D']:
                ws[f'{col}{row}'].border = border
                ws[f'{col}{row}'].fill = free_fill
            row += 1

        # 列幅調整
        ws.column_dimensions['A'].width = 20
        ws.column_dimensions['B'].width = 20
        ws.column_dimensions['C'].width = 30
        ws.column_dimensions['D'].width = 15

        wb.save(output_file)
        print(f"✓ {output_file} に保存しました")


def main():
    print("=== iCloudカレンダー空き時間分析ツール ===\n")

    # ユーザー認証情報
    email = input("iCloudメールアドレス: ").strip()
    password = getpass.getpass("パスワード（または アプリパスワード）: ")

    # アナライザー初期化
    analyzer = CalendarAnalyzer(email, password)

    if not analyzer.connect():
        sys.exit(1)

    # 対象週の開始日
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())

    print(f"\n対象週: {start_of_week.strftime('%Y-%m-%d')} ～ {(start_of_week + timedelta(days=6)).strftime('%Y-%m-%d')}")

    # イベント取得
    print("カレンダーからイベントを取得中...")
    events = analyzer.get_events_for_week(start_of_week)
    print(f"✓ {len(events)}件のイベントを取得しました")

    # 空き時間計算
    print("空き時間を計算中...")
    free_slots = analyzer.calculate_free_time(events, start_of_week)
    print(f"✓ {len(free_slots)}個の空き時間を検出しました")

    # Excel出力
    print("Excelファイルを生成中...")
    analyzer.export_to_excel(events, free_slots)

    print("\n完了！")


if __name__ == '__main__':
    main()
