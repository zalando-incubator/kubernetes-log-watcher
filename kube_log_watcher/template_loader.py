import os
from urllib.parse import quote_plus

from jinja2 import Environment, FileSystemLoader


template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
env = Environment(loader=FileSystemLoader(template_path))
env.filters["quote_plus"] = lambda x: quote_plus(x or "")


def load_template(tpl_name):
    return env.get_template(tpl_name)
