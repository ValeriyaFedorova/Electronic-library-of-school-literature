#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#Точка входа для запуска приложения "Электронная библиотека школьной литературы".
from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)