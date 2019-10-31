import math
import logging
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



class CacheLine(object):
    def __init__(self, tag=-1, dirty=False, valid=False, data=None):
        self.tag, self.data = tag, data
        self.dirty, self.valid = dirty, valid
    
    def __str__(self):
        return 'valid:' + str(self.valid) + ', dirty:'  + str(self.dirty) + ' tag:' + bin(self.tag)

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
        self.__SRAM = [[CacheLine() for i in range(self._setAssoc)] for x in range(self._sets)]
        self.__LRUQueue = [[i for i in range(self._setAssoc)] for x in range(self._sets)]
        self.__currentAddress = None
        self.queryCount = 0
        self.rdQuery = 0
        self.wtQuery = 0
        self.rdHit = 0
        self.wtHit = 0
        self.rdMiss = 0
        self.wtMiss = 0

    def __memory_store(self, address=None, data=None):
        if address == None:
            address = self.__currentAddress

    def __memory_load(self, address=None):
        if address == None:
            address = self.__currentAddress
        return None

    def _valid_list(self, setID):
        return [ line.valid for line in self.__SRAM[setID] ]

    def _tag_list(self, setID):
        return [ line.tag for line in self.__SRAM[setID] ]

    def _is_full(self, setID):
        return self._valid_list(setID).count(True) == self._setAssoc

    # Returns the way where the data stored
    def _index_tag(self, setID, tag):
        return self._tag_list(setID).index(tag)

    ############# implement replace policy #################
    def _replace_decide(self, setID):
        way = 0
        if self._replacePolicy == 'LRU':
            if self._is_full(setID):
                way = self.__LRUQueue[setID].pop(0)
                self.__LRUQueue[setID].append(way)
            else:
                way = self._valid_list(setID).index(False)
                q = self.__LRUQueue[setID]
                q.remove(way)
                q.append(way)
        else: raise NotImplementedError
        return way
    def _replace_update(self, setID, way):
        lruQ = self.__LRUQueue[setID]
        lruQ.remove(way)
        lruQ.append(way)
    ########################################################


    def _cache_data(self, setID, tag, data, makeDirty=False):
        cacheSet = self.__SRAM[setID]
        # Merge, comes from write hit or write after read
        if tag in self._tag_list(setID):
            line = cacheSet[self._index_tag(setID, tag)]
            line.data = data
            if makeDirty: line.dirty = True
            line.valid = True
        # Comes from read cache or write cache
        else:
            way = self._replace_decide(setID)
            line = cacheSet[way]
            # conflict, cache flush
            if line.dirty:
                self.__memory_store(self.__currentAddress, line.data)
            line.data = data
            line.tag = tag
            line.valid = True
            if makeDirty: line.dirty = True

    def _read_data(self, setID, tag, refresh=True):
        cacheSet = self.__SRAM[setID]
        # read hit
        if tag in self._tag_list(setID):
            way = self._index_tag(setID, tag)
            if refresh: 
                self._replace_update(setID, way)
            return ('Hit', cacheSet[way].data)
        # read miss
        else:
            return ('Miss', None)


    def query(self, record):
        self.queryCount += 1
        self.__currentAddress = record.address
        data = None
        setID = (record.address >> self._offsetWidth) % self._sets
        tag = record.address >> (self._bitWidth - self._tagWidth)
        memOp = record.memOp

   #     for line in self.__SRAM[setID]:
   #         print(line)
   #     print(self.__LRUQueue[setID])

        if memOp == MemoryOp.READ:
            self.rdQuery += 1
            status, data = self._read_data(setID, tag)
            if status == 'Miss':
                self.rdMiss += 1
                logging.info("Read Miss at {:b}".format(self.__currentAddress))
                data = self.__memory_load()
                self._cache_data(setID, tag, data)
            else:
                self.rdHit += 1
                logging.info("Read Hit at {:b}".format(self.__currentAddress))

        elif memOp == MemoryOp.WRITE:
            self.wtQuery += 1
            if self._writePolicy == 'through':
                self.__memory_store()
            elif self._writePolicy == 'back':
                status, data = self._read_data(setID, tag, refresh=False)
                if status == 'Miss':
                    self.wtMiss += 1
                    logging.info("Write Miss at {:b}".format(self.__currentAddress))
                else:
                    self.wtHit += 1
                    logging.info("Write Hit at {:b}".format(self.__currentAddress))
                self._cache_data(setID, tag, data, makeDirty=True)
            else: raise NotImplementedError

        else: raise NotImplementedError

    def print_config(self):
        print('size: %dKB, offset: %db, index: %db, tag: %db' % \
             (self._size/1024, self._offsetWidth, self._indexWidth, self._tagWidth))

    def print_record(self):
        if self.rdQuery == 0: rdMissRatio = 0
        else: rdMissRatio = self.rdMiss/self.rdQuery
        if self.wtQuery == 0: wtMissRatio = 0
        else: wtMissRatio = self.wtMiss/self.wtQuery
        print('Total Read:%d, Total Write:%d, ReadMiss:%d, WriteMiss:%d, Read Miss Rate:%f, Write Miss Rate:%f' % \
            (self.rdQuery, self.wtQuery, self.rdMiss, self.wtMiss, \
            rdMissRatio , wtMissRatio))



if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    c = Cache(size='128kB', setAssoc=4, writePolicy='back', blockSize='8B')
    c.print_config()
    with open('./traces/perlbench.trace', 'r') as trace:
        for line in trace.readlines():
            line = line.strip().split()
            c.query(MemRecord(line[0], line[1]))
    c.print_record()
      
    
    
      
