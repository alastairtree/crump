# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/alastairtree/crump/blob/main/htmlcov/index.html)

| Name                         |    Stmts |     Miss |   Cover |   Missing |
|----------------------------- | -------: | -------: | ------: | --------: |
| src/crump/\_\_init\_\_.py    |        5 |        0 |    100% |           |
| src/crump/cdf\_extractor.py  |      260 |       35 |     87% |47-48, 105, 114, 142-144, 193-194, 254, 269, 303, 314, 350, 465, 507-508, 547, 559-560, 575-576, 585-595, 605, 615, 632, 639, 665, 674-675 |
| src/crump/cdf\_reader.py     |      134 |       32 |     76% |90-91, 104-107, 115-118, 138-141, 175, 199-201, 219-220, 237-238, 254-256, 261-262, 274-276, 299-303 |
| src/crump/cli.py             |       15 |        0 |    100% |           |
| src/crump/cli\_extract.py    |      168 |       24 |     86% |32, 255, 275, 305-308, 337-342, 385, 391, 413-416, 445-450, 458-460 |
| src/crump/cli\_inspect.py    |      210 |       38 |     82% |35, 54-55, 64-65, 76-78, 121-122, 139, 161-163, 178-182, 191-192, 241-242, 257-258, 303, 312, 322-327, 342-346, 350-351, 398, 412-414 |
| src/crump/cli\_prepare.py    |      214 |       17 |     92% |235-238, 395, 417, 440, 474-475, 528, 546, 549-550, 552-553, 564-565, 571-572 |
| src/crump/cli\_sync.py       |      140 |       35 |     75% |51, 58-59, 170, 177, 181-184, 209-210, 222-238, 260-278, 287, 319-320, 334-335, 341-342 |
| src/crump/config.py          |      401 |       38 |     91% |57, 150, 153, 185-186, 193, 207-208, 309, 403, 480-481, 602, 649, 677, 680, 691, 706, 724, 727, 735-741, 763, 767, 770, 773, 778, 781, 804, 811, 880, 882, 884, 886, 937 |
| src/crump/console\_utils.py  |        8 |        1 |     88% |        24 |
| src/crump/csv\_file.py       |       51 |        1 |     98% |        81 |
| src/crump/database.py        |      642 |       55 |     91% |41-43, 67, 71, 75, 79, 83, 89, 93, 97, 103, 113, 123, 127, 139, 150, 174, 298, 358, 486-489, 650, 725, 781, 796, 802, 808, 816, 828, 842, 850, 858, 871, 892-899, 936, 969, 1048, 1052, 1141, 1156, 1161, 1165, 1259-1260, 1355-1356, 1476, 1482, 1658-1660 |
| src/crump/file\_types.py     |       37 |        1 |     97% |        82 |
| src/crump/history.py         |       37 |        0 |    100% |           |
| src/crump/parquet\_file.py   |       79 |        5 |     94% |12-13, 87, 188, 194 |
| src/crump/tabular\_file.py   |       76 |       20 |     74% |42, 53, 63, 72, 105, 116, 125, 161-164, 174, 202-212, 220 |
| src/crump/type\_detection.py |      100 |        2 |     98% |  160, 190 |
| **TOTAL**                    | **2577** |  **304** | **88%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/alastairtree/crump/main/badge.svg)](https://htmlpreview.github.io/?https://github.com/alastairtree/crump/blob/main/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/alastairtree/crump/main/endpoint.json)](https://htmlpreview.github.io/?https://github.com/alastairtree/crump/blob/main/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Falastairtree%2Fcrump%2Fmain%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/alastairtree/crump/blob/main/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.