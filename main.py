import datetime
import json
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from os import path

if len(sys.argv) < 1:
    raise RuntimeError('Config file location not specified')
config_file = sys.argv[1]
if path.isfile(config_file):
    with open(config_file) as f:
        config = json.load(f)
        server_config = config.get('server_config')
else:
    raise FileNotFoundError(f"Can't find {config_file}")


def date_parser(text):
    for fmt in ('%a %Y-%m-%d %H:%M:%S %Z', '%a %Y-%m-%d %H:%M:%S'):
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            pass
    raise ValueError('no valid datetime format found for: ' + text)


def time_since(var):
    if var is None:
        return 0
    if var == '':
        return 0

    var = date_parser(var)
    now = datetime.datetime.now()
    return time.mktime(now.timetuple()) - time.mktime(var.timetuple())


def time_until(var):
    if var is None:
        return 0
    if var == '':
        return 0

    var = date_parser(var)
    now = datetime.datetime.now()
    return time.mktime(var.timetuple()) - time.mktime(now.timetuple())


cmd = ["systemctl", "list-timers", "--all"]
p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
stdout = p.stdout
stdout = stdout.decode(sys.stdin.encoding)


def get_metrics():
    lines = stdout.strip().split('\n')

    header_line = lines[0]
    header_names = header_line.split()
    header_indexes = []
    header_range = {}

    for header_name in header_names:
        idx = header_line.index(header_name)

        header_indexes.append(idx)

    for idx, header_index in enumerate(header_indexes):
        next_index = idx + 1

        if next_index == len(header_indexes):
            header_range[header_names[idx]] = (header_index, None)
        else:
            header_range[header_names[idx]] = (header_index, header_indexes[next_index] - 1)

    parsed_entries = []

    for line in lines[1:-2]:
        parsed_entry = {}

        for header_name, (start_idx, end_idx) in header_range.items():
            parsed_entry[header_name] = line[start_idx:end_idx].strip()

        parsed_entries.append(parsed_entry)

    metrics_out = ''
    for parsed_entry in parsed_entries:
        labels = ''

        for entry in parsed_entry.items():
            if entry[0] == "NEXT" or entry[0] == "LAST":
                if entry[1] != "n/a":
                    labels += f'{entry[0]}="{time.mktime(date_parser(entry[1]).timetuple())*1000}", '
                else:
                    labels += f'{entry[0]}="{entry[1]}", '
            else:
                labels += f'{entry[0]}="{entry[1]}", '

        if parsed_entry["NEXT"] != "n/a":
            metrics_out += f'time_until_next_run{{{labels[:-2]}}}{time_until(parsed_entry["NEXT"])}\n'

        if parsed_entry["LAST"] != "n/a":
            metrics_out += f'time_since_last_run{{{labels[:-2]}}}{time_since(parsed_entry["LAST"])}\n'

        metrics_out += '\n'

    return metrics_out


class Exporter(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(bytes(get_metrics(), "utf-8"))
        # self.wfile.write(bytes(data.expose(), "utf-16"))


if __name__ == '__main__':
    web_server = HTTPServer((server_config['address'], server_config['port']), Exporter)

    try:
        web_server.serve_forever()
    except KeyboardInterrupt:
        pass

    web_server.server_close()
