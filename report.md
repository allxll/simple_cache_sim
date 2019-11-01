# 一个简单Cache模拟器的设计和作业

### 黄羽丰 2019310992 2019/11/1

本程序模拟了cache的基本行为，支持对地址的读写序列进行模拟，能够得到命中率和缺失率等cache的基本信息。本模拟器支持对cache的大小、组相联度、块大小、写回策略、预测策略进行定制，使用的替换策略为LRU(least recently used)。详细配置方法与参数请见Cache类的注释。

运行环境为`python3.7.3`，运行方法为
`python3 cache.py`

## 1. 
直接映射方法，size=128kB，block size = 8B，64bit，LRU替换策略，写通过(write through)方法，无路预测
* astar: 89.08%
* bzip2: 98.85%
* mcf: 98.42%
* perlbench: 95.40%

