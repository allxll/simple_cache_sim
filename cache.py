import math
from enum import Enum

class MemoryOp(Enum):
    READ = 0
    WRITE = 1

class MemRecord(object):
    readCount = 0
    writeCount = 0
    count = 0
    def __init__(self, mem_op, address):
        MemRecord.count += 1
        self.__address = int(address, 16)
        if mem_op == 'r':
            self.__memOp = MemoryOp.READ 
            MemRecord.readCount += 1
        else:
            self.__memOp = MemoryOp.WRITE
            MemRecord.writeCount += 1

    @property
    def address(self):
        return self.__address

    @property
    def memOp(self):
        return self.__memOp

    def __str__(self):
        return 'MemRecord *%s* at %16X' %  \
               (['READ ','WRITE'][self.memOp.value], self.address)

class Cache(object):
    
    def __init__(self, size='128KB', blockSize='8B', bitWidth=64, \
                 setAssoc=1, replacePolicy='LRU', predictPolicy=None, \
                 writePolicy='through'):
        unitDict = {'B':1, 'KB':1024, 'MB':1024**2, 'kB':1024}
        size_digit = "".join([digit for digit in size if digit.isdigit()])
        size_unit = "".join([char for char in size if char.isalpha()])
        blockSize_digit = "".join([digit for digit in blockSize \
                                 if digit.isdigit()])
        blockSize_unit = "".join([char for char in blockSize if char.isalpha()])
        self._size = unitDict[size_unit] * int(size_digit)  
        self._blockSize = unitDict[blockSize_unit] * int(blockSize_digit)
        self._bitWidth = bitWidth
        self._setAssoc = setAssoc
        self._replacePolicy = replacePolicy
        self._predictPolicy = predictPolicy
        self._writePolicy = writePolicy
        self._cacheLineMax = int(self._size / self._blockSize)
        self._sets = int(self. _cacheLineMax / self._setAssoc)
        self._offsetWidth = int(math.log2(self._blockSize))
        self._indexWidth = int(math.log2(self._sets))
        self._tagWidth = int(bitWidth - self._offsetWidth - self._indexWidth)
        self.__SRAM = [[] for x in range(self._sets)]
        self.queryCount = 0
        self.rdQuery = 0
        self.wtQuery = 0
        self.rdHit = 0
        self.wtHit = 0
        self.rdMiss = 0
        self.wtMiss = 0

    def _if_contain(self, setID, tag):
        return tag in self.__SRAM[setID]

    def _is_full(self, setID):
        return len(self.__SRAM[setID]) == self._setAssoc

    def _replace(self, setID, tag):
        if self._replacePolicy == 'LRU':
            self.__SRAM[setID].pop(0)
            self.__SRAM[setID].append(tag)
        else:
            raise NotImplementedError

    def _insert(self, setID, tag):
        if self._is_full(setID):
            self._replace(setID, tag)
        else:
            self.__SRAM[setID].append(tag)
        assert(len(self.__SRAM[setID]) <= self._setAssoc)
        assert(len(self.__SRAM[setID]) == len(set(self.__SRAM[setID])))

    def _refresh(self, setID, tag):
        assert(self._if_contain(setID, tag))
        if self._replacePolicy == 'LRU':
            self.__SRAM[setID].remove(tag)
            self.__SRAM[setID].append(tag)

    def query(self, record):
        self.queryCount += 1
        setID = (record.address >> self._offsetWidth) % self._sets
        tag = record.address >> (self._bitWidth - self._tagWidth)
        memOp = record.memOp
        if memOp == MemoryOp.READ:
            self.rdQuery += 1
            if self._if_contain(setID, tag):
                self.rdHit += 1
                self._refresh(setID, tag)
            else:
                self.rdMiss += 1
                self._insert(setID, tag)

        elif memOp == MemoryOp.WRITE:
            self.wtQuery += 1
            if self._writePolicy == 'through':
                pass
            elif self._writePolicy == 'back':
                if self._if_contain(setID, tag):
                    self.wtHit += 1
                    self._refresh(setID, tag)
                else:
                    self.wtMiss += 1
                    self._insert(setID, tag)
            else:
                raise NotImplementedError

        else:
            raise NotImplementedError


    def print_config(self):
        print('size: %dKB, offset: %db, index: %db, tag: %db' % (self._size/1024,\
             self._offsetWidth, self._indexWidth, self._tagWidth))

    def print_record(self):
        print('Total Read:%d, Total Write:%d, ReadMiss:%d, WriteMiss:%d, Read Miss Rate:%f, Write Miss Rate:%f' % (self.rdQuery, self.wtQuery, self.rdMiss, self.wtMiss, self.rdMiss/self.rdQuery, self.wtMiss/self.wtQuery))

if __name__ == '__main__':
    c = Cache(size='128kB', setAssoc=4, writePolicy='through', blockSize='16B')
    c.print_config()
    with open('./traces/astar.trace', 'r') as trace:
        for line in trace.readlines():
            line = line.strip().split()
            c.query(MemRecord(line[0], line[1]))
    c.print_record()
      
    
    
      
