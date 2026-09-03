import base64
import csv
import io
import os
import re
import sys
from datetime import datetime

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F1E0-\U0001F1FF"
    "☀-⛿"
    "✀-➿"
    "︀-️"
    "‍"
    "]+",
    flags=re.UNICODE,
)


def _strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text).strip()
try:
    import openpyxl
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    _OPENPYXL_OK = True
except ImportError:
    _OPENPYXL_OK = False

csv.field_size_limit(min(sys.maxsize, 2147483647))

def _get_logo_bytes() -> bytes | None:
    """Lê clickup_logo.png do diretório do exe/script (funciona em dev e no bundle PyInstaller)."""
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.dirname(sys.executable))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(meipass)
    candidates.append(os.path.dirname(os.path.abspath(__file__)))
    for base in candidates:
        path = os.path.join(base, "clickup_logo.png")
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
    return None


# --- bloco b64 legado (não utilizado) --- mantido apenas como fallback de último recurso
_CLICKUP_LOGO_B64_LEGACY = (
    "iVBORw0KGgoAAAANSUhEUgAAANAAAABQCAYAAABoFPusAAAABGdBTUEAALGPC/xhBQAAACBjSFJN"
    "AAB6JgAAgIQAAPoAAACA6AAAdTAAAOpgAAA6mAAAF3CculE8AAAAhGVYSWZNTQAqAAAACAAFARIA"
    "AwAAAAEAAQAAARoABQAAAAEAAABKARsABQAAAAEAAABSASgAAwAAAAEAAgAAh2kABAAAAAEAAABa"
    "AAAAAAAAAEgAAAABAAAASAAAAAEAA6ABAAMAAAABAAEAAKACAAQAAAABAAAA0KADAAQAAAABAAAAU"
    "AAAAAB4VuqkAAAACXBIWXMAAAsTAAALEwEAmpwYAAACaGlUWHRYTUw6Y29tLmFkb2JlLnhtcAAA"
    "AAAAPHI6eG1wbWV0YSB4bWxuczp4PSJhZG9iZTpuczptZXRhLyIgeDp4bXB0az0iWE1QIENvcmUg"
    "NS40LjAiPgogICA8cmRmOlJERiB4bWxuczpyZGY9Imh0dHA6Ly93d3cudzMub3JnLzE5OTkvMDIv"
    "MjItcmRmLXN5bnRheC1ucyMiPgogICAgICA8cmRmOkRlc2NyaXB0aW9uIHJkZjphYm91dD0iIgog"
    "ICAgICAgICAgICB4bWxuczp0aWZmPSJodHRwOi8vbnMuYWRvYmUuY29tL3RpZmYvMS4wLyIKICAg"
    "ICAgICAgICAgeG1sbnM6ZXhpZj0iaHR0cDovL25zLmFkb2JlLmNvbS9leGlmLzEuMC8iPgogICAg"
    "ICAgICA8dGlmZjpPcmllbnRhdGlvbj4xPC90aWZmOk9yaWVudGF0aW9uPgogICAgICAgICA8dGlm"
    "ZjpSZXNvbHV0aW9uVW5pdD4yPC90aWZmOlJlc29sdXRpb25Vbml0PgogICAgICAgICA8ZXhpZjpD"
    "b2xvclNwYWNlPjE8L2V4aWY6Q29sb3JTcGFjZT4KICAgICAgICAgPGV4aWY6UGl4ZWxYRGltZW5z"
    "aW9uPjI2MDwvZXhpZjpQaXhlbFhEaW1lbnNpb24+CiAgICAgICAgIDxleGlmOlBpeGVsWURpbWVu"
    "c2lvbj4xMDA8L2V4aWY6UGl4ZWxZRGltZW5zaW9uPgogICAgICA8L3JkZjpEZXNjcmlwdGlvbj4K"
    "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"
    "L47BbkIZ0BZYmWvwWJ/fU96cZUaN z64xdto+J+wgQPR9h4A8dkHkwcdKTt29wpaCESs/9fRpesB"
    "PHTssZDaqlqqLFfn9BPjQx9oih7qzBdObEwF17IToYzrF21BH2ergJ089tiWl7gsCZHNVLW2Mzyil"
    "pj0WOZvf9g9f89s/7f0uD3n/hgfPN318+8JhK+oXtve38de//Vzf9Sbv793Z+1tezTbs/IJpwwkeU"
    "4XJ6Ka5YBNM3pzpo8pD0Xiq2UE/2bEg5FpAmaNcpTpkW1BYH/EAYueK92+O0616VnqT/90aH++N6"
    "p3DAgX55OPjwmHM6c9UHpopWJ/Igp/0RWGKgP4LBXgIHlKA45LeJrDSQwQa9D6Ba/Rv+pkeIw0gs"
    "yv6Wx+kBvqzwKF/0MgW8KOTzQM6QzZf1dLG+KzuRD7lpy/O+tc9fKOfuvjz6KH6lP3+QSt68aSOR"
    "9SRrAVvOM3ftPP13O/wt0LD2HlobqsYE/6kYMYkNeOvVH6qANmkVUuDf8Z56ccm5Crlkd9qAHFEg"
    "w4XkBN35rj+5OthY6Ke/s2Zpym/V43fHMmu/VX1bxJ+Wrtu/eGgFjwLlLegIbhtrBszgBhjfLz1t"
    "rDxWT0BRv63wkQBMv+oljbGZ38QabeRdrpJ0ZM1/phuhOQLenDtkSWZBA4B1PyxzXo3PbZSBSstBs"
    "TopOZIjyg/WYBaNehoBdB90sEcdZHy6Bl3BNN5meoLwoHCu4XjhV8L8OMoNsZVyl8nsKu9S7BxEx"
    "y2Yzyv/BO1axb0XLP8NcpzKmCMtjMOFkCm4/regcwu7M4XCwcLZouHlGesxkMe2JiOUB5iXBufa"
    "kGkR9Laefhy6SgRARPtRlEwteTcFkCvlko8IsaI5lw20Q+qjptvqFXdaWdOdZXy8cmyfpo5wj2gt"
    "tyLvVkwJzdHNzk4+1ShnngoYX2zq7JrIMcofg9kMi1FX1uhyZvjXVprTOBY8FBlY32f8tbWZJme6"
    "zOATL+l6n83FKoj5uM7ArqZPvH8jTV+849asflkVCOPx9EEDn+B2rwKQ3Py5kcLrWTrLVAhMsbQj"
    "RpzYESM3ogmqNIcotH1DVnHxBPgbxcsj+NiVyufqPwSgfcdOD0ED8etk4Xlwn0C9ywQ93XwNZobZ"
    "EL0aTYgj7wvC6fX6qlr1F7VLZP13bIANTxDWCywa9vugm8z3k8LBNeugo3J+nyb6lioaEMdwTUsaj"
    "nyBuoleqcz0MUR1muEwx5grUtr90+VeewKWR02wCl2EmwHGo5dcLLh8It9SGIymezX1jjNaUnp7wH"
    "hwVqegIEX4DDowpHtNIHgISBoM9DCoUv9BF89basKqzeb1fNsjLIFwx/V+S01Hblvox47YQsWDXbh"
    "7wmQ2QD7QlsKm0e5Fj9Ge+JdR4dPd9R+OLFFnRo261jg0wUdDRtebL4SZ3uqjh2ZGB1jH1S71sz"
    "OTDv4bMLIj5aDIQfYgwSbcAsk7ldwFqtXtp/goZ6jHMHDrouOzdiOtjYGgoZ2Rwr/JSDHdidl1y"
    "Frs05lrWD9DsTTaAyN5NTXmTwevxMkVo7zWd3TtUr6os76ZPdh14Ksrlpq8tMG1yT74Gyd0322q"
    "yuodOkrOoV2fWdtlKi94DNds4JKQUfD9oUtycVoOATpr2tqmXEp2grLqr21wJbO0agRYWiCjfasaJ"
    "8R9q3lmZC4XBVbIptMnBaql0lwQMZXLa39pJ7FgnbNzgO8+EN9X+gwW3ivwKreKIiopx391refojrI"
    "bFwtrQ1odgGj+vHYI3i73ijF5lCjvqtX1p3LeB8sEMzhxqf5Ch60OP3A3p1P2793R/LzO6t15Ful"
    "zvlVGYdc17uzdqEtkGN1w5RpE9iudkwyjmErLmUMSXq/sIkAESiMCyc0xB2ooHra/F14iwDZinaV"
    "8lwjGEnpjrSZhwiLxIczn1prY21Nx6dU/1oBQkcjnAP9GOsuVlmrs0B6j8qmj43f0mW6xs5GP1Znff"
    "9NdTsJkNnSZO6tOu65aINTIt/S3ytvfAQ+eXQ0vX+kvOlDCiwgj1Le6Exl4tdM/j9U//oak8mkaL"
    "Ygf41AW5sLa8uYbK7jgaXqDUQFveux4Pmv95TazzvE//Xcw8LFH9vHR4p1jiCIOhZUX9DOnLdyiy"
    "PvqjzacUfx4YNv7nsDQyOIhnmkMwONU/P7hPhkkAfmoIuVx9EGon11ga+F0MZW+heU30sw+m9luG6"
    "TZo7YbADhZAfUZJgzI8+ca57yA9FMXeCY901hSo3JnItxIQd9kAsYN051sMAuHNc73uciXUMvgtu"
    "gbPQXun9QCq/ZMJ6/GqYGdIrq4DOHJo8+ZqvpyhvVBxC8xvcdY1Ia14vqAwX40AvZ8XY/Vdn8Qt"
    "kNTBzZrMu57f4zF870q+YeHPrzD/d+bkd4x4dn/B1ndYUOb5Nn7EOm2m2iNjO+7Md96IfhPR+6y/"
    "tZ4L7KP95/d99RCOD90PTaDjWkwCqD6XsozQWcOz551JmDEhg/E84XOoUThAsF6uzMbU5oQcIKboH"
    "3LeWtj/ikNRNA96stR8iJwt9qckxPnMDyVyq/tYAT4DjjhU8JKwT6BH8VqLM5mFGrN93NsVjJNxeg"
    "u4S47vG8BW5GPPRrNr2h1sbsRxtzWPK/EuYIxwkEKXak3vonDywoHlb+VYLtdo0CKG6Lq8Q7SYCA"
    "BcQ8MyfINZuRt/ni6SLEWDYs2epfmO5fdcE7/fVfmeH9uQdUSrNnlkpnvbdUOvdI72cfGd5+9PuX"
    "b4pmhaN9m7UZTFN4jr7Gs9W7mYVlEz78g/LtH7nd+44fFIuH31osHnZPOez4hfeHdBfnH3ybj75S"
    "UuBvi5ojJtyMda3yGJMjC2kccSeI18fz9TyrazKeVQpdIcBvO5Q5RjMB1K120eKjlABGTlxPHMec"
    "k2B+QMAhLdjgR7+4jr9XmYDcV+C66WMOTADtJEA7CE8JJoeU/szxjlEeIijNnu9XHic1ebSxdtRZ"
    "OZ7Cb+OwehvnHF2DzA5nKg9PfEyU44HxnMp3CAuE3wkmO96/9ckT2akCZEFaLQ3j0wY/jCYKBh3b"
    "Cvo4Z3pxj7Ft7hvptJu+qhSWKln9PkKgPwqSO/f0Vsr58emDtp0w8Z6TjyweX/h28AidcKT70zbO"
    "t0eDm+vmzJnj5861QbdWjZ22dkHhBCYg6P3gpSt2yW4+9upUJr1Xz6qyvtntstGvxpXCMFzjy/lX"
    "ZTuL4ytvOegXa04q3DVG31ydo675wsKgxHWMCnHzv53wTgHHwBkIMIhV1XhJqSeFyBOwtvJSxwSN"
    "raWzqRBFi4BSkxlVDuPD2l2qNkcJrxFwnrieOAO7zr6CEXW0Nf1wSHYzdhfGEHcWG5OqI0I+9D/"
    "Cp4UfC/iI2cDafl11jwq/EdCH+luFuwWOTKanspEuXEcvk0M9ZPKqpWo77Eb/82uVtBuMmAvkMq+"
    "ThZmCEXVci/fDXGMPdtIlAuNj/loiGg+L2CF4GnbB7n7zvMvepB9F2HZFOezVs7E2NI3UVSJnzv"
    "T0lUvZsZnd2nKZB07trFyyJtNz+eWXB3+HrZsPkXYPksgA3cocfYnf1I+pfMK1BacF6WCzvpWlkl"
    "51mTMwHfpqT5jqW9bXk906v3t5Ze4HM/Zyu8hj1uhVa6oQDPkSF6NiUG56Pyh8V2gXzIhcwwFB3P"
    "AqrkPobE6BfsgvXrhJgIaa+CrXwJ/omRewF3JxZpw17pzoZ3ooGwW26Uy9Ocsq5d8nrBAI9KEIB7"
    "tNuEj4vIBt8BVk0z/3t98W9hRWCoyf8X5cuFeYKsBHPXaETK9qad1PdIWf8UInCoyb8WKHoQge+o"
    "nbon7+uMZpgLH9XLhAgJqRX+Vs8NlCAAUh73rO7HIvfnVPd34x9JenUi4v64XSmF8FiUjfSFAQpb"
    "LFYqjfhUuNz7cFszV3R598UuXOIJf6SSlbfCIdlJb36TvVvWn94VA+v2MpXT7A5Sr/kR6T3r6oYe"
    "k/byi6rP7QiO8gxEj7TKg/724r6We2U2F45t0HZFZH74n0qDvGNlgWPsa+VMCxLhQ+KUB0xvHGJt"
    "5Su0YK4RBmv27lPyNwTMJBefxquuB8rJLIhN/qlY0mj/4seEnNGblOG8p3C7OEawW+McMkIwfdAP"
    "IhkuVKuzYBRzxMWCxAOCpEX/Ahi/amg7JR4FE3W3ibsL/AToZM6gmaXYXLhI8KNranlecod6PwBg"
    "HiGmQ6VkvVT/o3XQke7PZh4U6BvtCVIBqMsIMFJ33Rj80Z1yDGCA/Bw86JLW08pp+qhk+NBjWkFN"
    "71wHTKL4MrdGg7Z2xWv+nhownlV3f62+smX0PxuUpYqfT0VaRo8Op8PtWZyvibApf5XTnV9oQLxj"
    "yRT2f+EOT8bfmxmZNSqfT2CpxSpVxUH7XgqYnUtxwwt/4a1oW5iTmdFP2ZP94zpx808SneE/V33F"
    "wGh8GoOAM32e8WFgqs0kwezg7gMVgdKZONU35E2E8geGinjoijQwQU/EwetGk1iT453zM6HD3Ow71"
    "dbdSRXen/h8I7hJ8IOJbpyDXmEZBHDtc4418nTBdYcW11t5Q+4aNMyisC8wecmv5xruOFfwjoj2z"
    "ADgQx9i9FubWB8JjK2ONy4XkB2QDd6mG6cv94h7CbcLNA/VCObfNNf2cJNm/0EbcHZfqHn8B+p/"
    "A3oZk+xDY4IaQlqlrYB6c/EMy5qL00blw+c8oKBYqCpiLLo3SVxKiY0m/HubQCKSz3+bCSVljlU"
    "zn9THZOu5dGFuovtyuhMpVQdzr6deysjoCKFXoRIUP/Qn7ySqGan5TNFHvLF926V/bCgi/o2GaMV"
    "fZhfGJUM/ZC5cE+wgzhTcLWAs7CBBAYBBvOxCrWLdwlQDgbcph0GzurKAPAkbEz7QmqRYLR/cpMF"
    "uChHfqMFx4XbKdABisoMgjSmcKBwiHC6wUcnyCFb5WwVHhYuFl4SICQbQ75pPLXCqzA6E27nEDbl"
    "wQjdGHcTwsfEj4mICfjtHZcZ0yMAbsgi+svCCxKlwmHCbsLU4TMBPrCFjj8/wq/E24T7hMgs1W1N"
    "PQnulwgMBefEN4kMG8sDH0CQUyQ3SDcIUDYAx1GTHTeMnGUs93ogv0rc9PZ1NlrZMNKNizpnihbkS"
    "l40K2AcKHywOu/ztLPLrowrb/91s8vRtf1Wz7KB9W8thh4Zeb+NuTTrhTmgmx6UkaZ8nk3vyM7G8"
    "WbvO9pZozqNaK4YSepBgfhGg5FAOEcRjgLiLfhmjkY+UY01PVGbair749dAeclhdBvqYAjQ+hN8I"
    "FWyQJ7sPb1PIyPvi1oabuVYAGELQlGAshshwz0rtdVsx8tJmcqPV9Apjwomg/aEBwE6BoB2lzYRm"
    "CHJYCeq0HJqNgDOf00ogBCSodbkO5y+nUd0bkz/LEKnm+m21KZniAshWkfKAgyvNHpDwb9tZB+Mr"
    "5alhmioJEZoiCjrOv9AaR6BVtFPGF6k2y2qJ+W8zn/yZv2z10R9a3vx7VwdKPpQIQ9mBQclclkcs"
    "0ZlY0Ixxjseo0tkoOseHvk4yBxpxmKx+RZas5Jipx6hzP94v1YW1La4YD1eg00XtqYzHgb6uvHQ1"
    "2cGBsYSBeTO9B1ZA0VQI+K560wiuiLoKknxgvFA7paM8JPHGFERPAU9Fh7gXaj2XcH3+otVfYMw8"
    "ovxmRT2Wwmze/E6dCmnyqNniqoq9o9EpaPSFNSzddqlOgvifSgzZd1jOtNZ/QjcQoezcHDGv4+BA"
    "8PDLT1tHLfY70OlJoTcXzCOVHKnIAUe7FYcJ3JqHcoVfUTfPAgx2BlY2qGx3gtpU/koAM0kH702Y"
    "isvelEanoNNJ44T327aPFs1JHqzFak2C6uK3kCx2ytbEvEHAGzZX0/lE3/ljoYrBErwIipoBMYP1P"
    "Fd99OuDJ4qHP64ndN2u6Np+bHZj82Np+eWpapevWfA5UVFcQRP/CrjMKEcVfvdDRzPFvTDZIu6KF"
    "EdkwuE4x1GUXeM30rStc+17P0vO5jXtfbudhnr9xNv6O9/glnGsihmu29mfbN8AzUHw7YCrXSZyt"
    "tTDfajqS9yRkq3VD99OuBB48qsRM9Ps3pD0iD8FMH9Wy3yebpQ9NtmcNLqWDvzDgtOQrZktYEgko"
    "PE3QkUx0bLLd8ghd4hK304WJQvnnNmp6uWzon/El7UtDe7dLd+wWsJgn9+1ig2SOc7YQbIlD7rT/"
    "qAYRk7SnBSTNd7tI79b8wiDo7Xpw4Zvz4XbJj0/soYN5eTvupCqTJlWzQpvubQA8cehVEy8K8/4v"
    "PBYsrYXHR6t7iY12fm/gi7fle3LTHXZmgpJzQv5UFLIA+r1F/UeBhAUsuAcODgkeEt9fKSjbITkc"
    "/Ea2XADLhPKXbbDOXuvLKdY9cBd0zLS24Nv2ndGNK+ZXBctfb6x7bokdP9AiQ/hWEb1wv38yFo/y"
    "gwNRL0leGBSyAzpG6sxuo/IzqdhAIqFf+Ea7BABlX0NHhUtOmRTd74UA7CV8TEnPqsV2d7+rQHdH"
    "Q321r3F1S+//JAtync2zvEI4V2IGoY7FlB1oi8C0QO530L8CqW++0XneggbXXz1RpmHyJFJ45c6q"
    "PE5KAGdhiyZWXpwU2UgC9PI2RaPWytgCnEz12+hdix9loD5aSAPqX+UgqXqYWGMxXN+ix7WVqn0S"
    "txAKJBRILJBZILJBYILFAYoHEAokFEgskFkgskFggsUBigcQCiQUSCyQWSCyQWCCxQGKBxAKJBRIL"
    "JBZILJBYILFAYoHEAokFEgskFkgskFggsUBigcQCiQUSCyQWSCyQWODfwwL/B9shJRWna+7eAAAA"
    "AElFTkSuQmCC"
)

_STANDARD_COLS = [
    "Task Type", "Task ID", "ClickUp URL", "Task Name", "Status", "Task Content",
    "Assignee", "Priority", "Latest Comment", "Comment Count", "Assigned Comment Count",
    "Due Date", "Start Date", "Date Created", "Date Updated", "Date Closed", "Date Done",
    "Created By", "Space", "Folder", "List",
    "Subtask ID's", "Subtask URL's", "tags", "Lists", "Sprints",
    "Linked Tasks", "Linked Docs",
    "Time Logged", "Time Logged Rolled Up", "Time Estimate", "Time Estimate Rolled Up",
    "Points Estimate", "Points Estimate Rolled Up",
]


def _cf_type_label(api_type: str) -> str:
    return {
        "drop_down": "drop down",
        "short_text": "short text",
        "long_text": "long text",
        "text": "text",
        "date": "date",
        "users": "users",
        "labels": "labels",
        "tasks": "tasks",
        "email": "email",
        "phone": "phone",
        "url": "url",
        "checkbox": "checkbox",
        "currency": "currency",
        "number": "number",
        "automatic_progress": "automatic progress",
        "manual_progress": "manual progress",
        "emoji": "emoji",
        "rating": "rating",
        "location": "location",
    }.get(api_type, api_type.replace("_", " "))


def _cf_column_name(cf: dict) -> str:
    name = cf.get("name", "").strip()
    cf_type = _cf_type_label(cf.get("type", ""))
    if not name:
        return ""
    return f"{name} ({cf_type})"


def _ordinal_suffix(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _format_date(ts_ms) -> str:
    """Formata timestamp ms → 'yyyy-MM-dd' em UTC (evita desvio de fuso horário)."""
    if not ts_ms:
        return ""
    try:
        dt = datetime.utcfromtimestamp(int(ts_ms) / 1000)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _format_datetime(ts_ms) -> str:
    """Formata timestamp ms → 'yyyy-MM-dd' em UTC (evita desvio de fuso horário)."""
    if not ts_ms:
        return ""
    try:
        dt = datetime.utcfromtimestamp(int(ts_ms) / 1000)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _format_ms(ms) -> str:
    """Milissegundos → 'Xh Xm'."""
    if not ms:
        return ""
    try:
        total_min = int(ms) // 60000
        h = total_min // 60
        m = total_min % 60
        parts = []
        if h:
            parts.append(f"{h}h")
        if m:
            parts.append(f"{m}m")
        return " ".join(parts) or "0m"
    except Exception:
        return ""


def _format_tis(minutes) -> str:
    """Minutos → formato nativo ClickUp: 'X hours' ou '<1 Hour'."""
    if minutes is None:
        return ""
    try:
        total = int(minutes)
        if total <= 0:
            return ""
        hours = total // 60
        return "<1 Hour" if hours == 0 else f"{hours} hours"
    except Exception:
        return ""


def _resolve_cf(cf: dict) -> str:
    val = cf.get("value")
    if val is None or val == "":
        return ""
    cf_type = cf.get("type", "")
    if cf_type == "drop_down":
        options = cf.get("type_config", {}).get("options", [])
        try:
            idx = int(val)
            for opt in options:
                if opt.get("orderindex") == idx:
                    return _strip_emoji(opt.get("name", ""))
        except (ValueError, TypeError):
            pass
        return _strip_emoji(str(val))
    if cf_type == "date":
        return _format_date(val)
    if cf_type == "users":
        if isinstance(val, list):
            names = [u.get("username", "") for u in val if isinstance(u, dict)]
            return "[" + ", ".join(names) + "]" if names else "[]"
        return str(val)
    if isinstance(val, list):
        return _strip_emoji(", ".join(str(v) for v in val if v is not None))
    return _strip_emoji(str(val))


def _build_cf_index(task: dict) -> dict:
    result = {}
    for cf in (task.get("custom_fields") or []):
        col_name = _cf_column_name(cf)
        if col_name:
            result[col_name] = _resolve_cf(cf)
    return result


def _extract_standard_fields(task: dict, space_name: str, folder_name: str, list_name: str) -> dict:
    subtasks = task.get("subtasks") or []
    sub_ids = [s.get("id", "") for s in subtasks if isinstance(s, dict) and s.get("id")]
    sub_urls = [
        s.get("url") or f"https://app.clickup.com/t/{s.get('id', '')}"
        for s in subtasks if isinstance(s, dict) and s.get("id")
    ]
    st_ids = "[" + ", ".join(sub_ids) + "]" if sub_ids else ""
    st_urls = "[" + ", ".join(sub_urls) + "]" if sub_urls else ""

    tags = ", ".join(t.get("name", "") for t in (task.get("tags") or []))
    priority = (task.get("priority") or {}).get("priority", "none")
    creator = (task.get("creator") or {}).get("username", "")
    assignees_raw = task.get("assignees") or []
    if assignees_raw:
        names = [a.get("username", "") for a in assignees_raw if isinstance(a, dict)]
        assignees_str = "[" + ", ".join(names) + "]"
    else:
        assignees_str = "[]"
    status = (task.get("status") or {}).get("status", "")

    return {
        "Task Type": "Task",
        "Task ID": task.get("id", ""),
        "ClickUp URL": task.get("url", "") or f"https://app.clickup.com/t/{task.get('id', '')}",
        "Task Name": _strip_emoji(task.get("name", "") or ""),
        "Status": status,
        "Task Content": _strip_emoji(task.get("description", "") or ""),
        "Assignee": assignees_str,
        "Priority": priority,
        "Latest Comment": "",
        "Comment Count": task.get("comment_count", 0),
        "Assigned Comment Count": 0,
        "Due Date": _format_date(task.get("due_date")),
        "Start Date": _format_date(task.get("start_date")),
        "Date Created": _format_datetime(task.get("date_created")),
        "Date Updated": _format_datetime(task.get("date_updated")),
        "Date Closed": _format_datetime(task.get("date_closed")),
        "Date Done": _format_datetime(task.get("date_done")),
        "Created By": creator,
        "Space": space_name,
        "Folder": folder_name or "",
        "List": list_name,
        "Subtask ID's": st_ids,
        "Subtask URL's": st_urls,
        "tags": tags,
        "Lists": f"[{list_name}]" if list_name else "[]",
        "Sprints": "[]",
        "Linked Tasks": "",
        "Linked Docs": "",
        "Time Logged": _format_ms(task.get("time_spent")),
        "Time Logged Rolled Up": "",
        "Time Estimate": _format_ms(task.get("time_estimate")),
        "Time Estimate Rolled Up": "",
        "Points Estimate": task.get("points", "") or "",
        "Points Estimate Rolled Up": "",
    }


def _extract_tis(tis_data: dict) -> dict:
    """Extrai {status_name: tempo_formatado} dos dados Time In Status."""
    result = {}
    if not tis_data:
        return result
    current = tis_data.get("current_status") or {}
    if current.get("status"):
        minutes = (current.get("total_time") or {}).get("by_minute", 0)
        result[current["status"]] = _format_tis(minutes)
    for entry in (tis_data.get("status_history") or []):
        s = entry.get("status")
        if s and s not in result:
            minutes = (entry.get("total_time") or {}).get("by_minute", 0)
            result[s] = _format_tis(minutes)
    return result


class ExcelBIWriter:
    def __init__(self, base_dir: str, suffix: str = "Geral"):
        safe = (
            "".join(c for c in suffix if c.isalnum() or c in " -_")
            .strip().replace(" ", "_") or "Consolidado"
        )
        self.base_dir = base_dir
        self.suffix = safe
        self.filepath = os.path.join(base_dir, f"Relatorio_BI_{safe}.csv")
        self.xlsx_path = os.path.join(base_dir, f"Relatorio_BI_{safe}.xlsx")
        self._rows = []
        self._cf_order = []
        self._cf_seen = set()
        self._tis_order = []
        self._tis_seen = set()

    def append_task(self, task: dict, tis_data: dict = None,
                    space_name: str = "", folder_name: str = "", list_name: str = ""):
        self._rows.append((task, tis_data or {}, space_name, folder_name, list_name))
        for cf in (task.get("custom_fields") or []):
            col_name = _cf_column_name(cf)
            if col_name and col_name not in self._cf_seen:
                self._cf_seen.add(col_name)
                self._cf_order.append(col_name)
        if tis_data:
            current = tis_data.get("current_status") or {}
            if current.get("status"):
                tis_col = f"[TIS] {current['status']}"
                if tis_col not in self._tis_seen:
                    self._tis_seen.add(tis_col)
                    self._tis_order.append(tis_col)
            for entry in (tis_data.get("status_history") or []):
                s = entry.get("status")
                if s:
                    tis_col = f"[TIS] {s}"
                    if tis_col not in self._tis_seen:
                        self._tis_seen.add(tis_col)
                        self._tis_order.append(tis_col)

    def _build_row(self, task, tis_data, space_name, folder_name, list_name, all_cols):
        std = _extract_standard_fields(task, space_name, folder_name, list_name)
        cf_idx = _build_cf_index(task)
        tis_idx = {f"[TIS] {k}": v for k, v in _extract_tis(tis_data).items()}
        row = []
        for col in all_cols:
            val = std.get(col)
            if val is None or val == "":
                val = cf_idx.get(col)
            if val is None or val == "":
                val = tis_idx.get(col, "")
            row.append("" if val is None else val)
        return row

    def finalize_xlsx(self):
        os.makedirs(self.base_dir, exist_ok=True)
        all_cols = _STANDARD_COLS + self._cf_order + self._tis_order

        # ── CSV ──────────────────────────────────────────────────────────────
        with open(self.filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(all_cols)
            for (task, tis_data, space_name, folder_name, list_name) in self._rows:
                writer.writerow(
                    self._build_row(task, tis_data, space_name, folder_name, list_name, all_cols)
                )

        # ── XLSX ─────────────────────────────────────────────────────────────
        if not _OPENPYXL_OK:
            print("  [XLSX] openpyxl nao instalado — gerando apenas CSV.")
        try:
            if not _OPENPYXL_OK:
                raise ImportError("openpyxl nao disponivel")
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Tasks"

            # Logo ClickUp nas linhas 1-2, clicável para https://app.clickup.com
            try:
                logo_bytes = _get_logo_bytes()
                if not logo_bytes:
                    raise ValueError("clickup_logo.png nao encontrada")
                img = XLImage(io.BytesIO(logo_bytes))
                img.width = 140
                img.height = 45
                img.anchor = "A1"
                ws.add_image(img)
                ws["A1"].hyperlink = "https://app.clickup.com"
            except Exception as logo_err:
                print(f"  [Aviso] Logo nao inserida: {logo_err}")

            ws.row_dimensions[1].height = 25
            ws.row_dimensions[2].height = 25

            # Estilos do cabeçalho (azul escuro, idêntico ao export nativo)
            header_fill = PatternFill("solid", fgColor="1F3864")
            header_font = Font(bold=True, color="FFFFFF", size=11)
            header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
            thin = Side(style="thin", color="CCCCCC")
            border = Border(left=thin, right=thin, top=thin, bottom=thin)
            data_align = Alignment(vertical="top", wrap_text=False)

            # Cabeçalho na linha 3
            for col_idx, col_name in enumerate(all_cols, 1):
                cell = ws.cell(row=3, column=col_idx, value=col_name)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = header_align
                cell.border = border
            ws.row_dimensions[3].height = 35

            # Dados a partir da linha 4
            for row_idx, (task, tis_data, space_name, folder_name, list_name) in enumerate(self._rows, 4):
                for col_idx, val in enumerate(
                    self._build_row(task, tis_data, space_name, folder_name, list_name, all_cols), 1
                ):
                    if isinstance(val, str) and len(val) > 32767:
                        val = val[:32764] + "..."
                    cell = ws.cell(row=row_idx, column=col_idx, value=val)
                    cell.border = border
                    cell.alignment = data_align

            # Larguras de coluna
            for col_idx, col_name in enumerate(all_cols, 1):
                col_letter = get_column_letter(col_idx)
                if col_name == "Task ID":
                    ws.column_dimensions[col_letter].width = 18
                elif col_name in ("Task Name", "Task Content", "Folder"):
                    ws.column_dimensions[col_letter].width = 45
                elif col_name.startswith("[TIS]"):
                    ws.column_dimensions[col_letter].width = 16
                elif col_name in ("Date Created", "Date Updated", "Date Closed", "Date Done"):
                    ws.column_dimensions[col_letter].width = 38
                else:
                    ws.column_dimensions[col_letter].width = 25

            ws.freeze_panes = "A4"
            last_col = get_column_letter(len(all_cols))
            last_row = 3 + len(self._rows)
            ws.auto_filter.ref = f"A3:{last_col}{last_row}"

            wb.save(self.xlsx_path)
            print(f"\n  [Excel] Arquivo gerado: {self.xlsx_path}")
        except Exception as e:
            print(f"\n  [Aviso Excel] Nao foi possivel gerar XLSX: {e}")

