import math
import logging
from enum import Enum


class MemoryOp(Enum):
    READ = 0
    WRITE = 1


class MemRecord(object):

    def __init__(self, mem_op, address):
        self.__address = int(address, 16)
        if mem_op == "r":
            self.__memOp = MemoryOp.READ
        else:
            self.__memOp = MemoryOp.WRITE

    @property
    def address(self):
        return self.__address

    @property
    def memOp(self):
        return self.__memOp

    def __str__(self):
        return "MemRecord *%s* at %16X" % (
            ["READ ", "WRITE"][self.memOp.value],
            self.address,
        )


class CacheLine(object):
    def __init__(self, tag=-1, dirty=False, valid=False, data=None):
        self.tag, self.data = tag, data
        self.dirty, self.valid = dirty, valid

    def __str__(self):
        return (
            "valid:"
            + str(self.valid)
            + ", dirty:"
            + str(self.dirty)
            + " tag:"
            + bin(self.tag)
        )

    def clear(self):
        self.tag = None
        self.data = None
        self.valid = False
        self.dirty = False

    def swap(self, otherLine):
        self.tag, otherLine.tag = otherLine.tag, self.tag
        self.data, otherLine.data = otherLine.data, self.data
        self.dirty, otherLine.dirty = otherLine.dirty, self.dirty
        self.valid, otherLine.valid = otherLine.valid, self.valid

    def memory_store(self):
        assert(self.dirty and self.valid)
        self.dirty = False

    def memory_load(self, address, tag):
        self.tag = tag
        self.dirty = False
        self.valid = True
        self.data = None

    def calc_address(self):
        return None

class Cache(object):
    '''
    @size: capacity of the cache
    @blockSize: size of a cache line
    @bitWidth: bit width of the address
    @setAssoc: set associativity of the cache
    @replacePolicy: only 'LRU' supported
    @predictPolicy: 
        None: no prediction
        'MRU': most recently used cache line in a set
        'MC': multi-column prediction method, which is a modification 
              of a column associative cache. Note that when applying this
              value, only write through policy produce the right statistic
              number at this time. 
    @writePolicy:
        'through': write through policy. no cache for write
        'back': cache write and refresh when eviction happens
    '''
    def __init__(
        self,
        size="128KB",
        blockSize="8B",
        bitWidth=64,
        setAssoc=1,
        replacePolicy="LRU",
        predictPolicy=None,
        writePolicy="through",
    ):
        unitDict = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "kB": 1024}
        size_digit = "".join([digit for digit in size if digit.isdigit()])
        size_unit = "".join([char for char in size if char.isalpha()])
        blockSize_digit = "".join([digit for digit in blockSize if digit.isdigit()])
        blockSize_unit = "".join([char for char in blockSize if char.isalpha()])
        self._size = unitDict[size_unit] * int(size_digit)
        self._blockSize = unitDict[blockSize_unit] * int(blockSize_digit)
        self._bitWidth = bitWidth
        self._setAssoc = setAssoc
        self._replacePolicy = replacePolicy
        self._predictPolicy = predictPolicy
        self._writePolicy = writePolicy
        self._cacheLineMax = int(self._size / self._blockSize)
        self._sets = int(self._cacheLineMax / self._setAssoc)
        self._offsetWidth = int(math.log2(self._blockSize))
        self._indexWidth = int(math.log2(self._sets))
        self._tagWidth = int(bitWidth - self._offsetWidth - self._indexWidth)
        # the memory where cachelines resides in
        self.__SRAM = [
            [CacheLine() for i in range(self._setAssoc)] for x in range(self._sets)
        ]
        # for the implementation of LRU replacing policy and MRU prediction 
        self.__LRUQueue = [
            [i for i in range(self._setAssoc)] for x in range(self._sets)
        ]
        self.__currentAddress = None
        self.__currentMemOp = None
        # for the implementation of Multi-column prediction
        self.__MCLocList = [[[ False for j in range(self._setAssoc)] for i in range(self._setAssoc)] for x in range(self._sets)]
        self.queryCount = 0
        self.rdQuery = 0
        self.wtQuery = 0
        self.rdHit = 0
        self.wtHit = 0
        self.rdMiss = 0
        self.wtMiss = 0
        self.firstHit = 0
        self.nonFirstHit = 0

    def __memory_store(self, address=None, data=None):
        if address == None:
            address = self.__currentAddress
    def __memory_load(self, address=None):
        if address == None:
            address = self.__currentAddress

    def _valid_list(self, setID):
        return [line.valid for line in self.__SRAM[setID]]

    def _tag_list(self, setID):
        return [line.tag for line in self.__SRAM[setID]]

    def _is_full(self, setID):
        return self._valid_list(setID).count(True) == self._setAssoc

    def _index_tag(self, setID, tag):
        ''' Returns the way where the data stored '''
        return self._tag_list(setID).index(tag)

    def _replace_decide(self, setID):
        '''
        decide which way to save the newly obtained data.
        '''
        way = 0
        if self._replacePolicy == "LRU":
            if self._is_full(setID):
                way = self.__LRUQueue[setID][0]
            else:
                way = self._valid_list(setID).index(False)
        else:
            raise NotImplementedError
        return way

    def _replace_update(self, setID, way):
        '''
        update LRU queue after a reference is served
        '''
        lruQ = self.__LRUQueue[setID]
        lruQ.remove(way)
        lruQ.append(way)

    def _mc_swap(self, setID, majorWay, way):
        ''' multi-column swap together with LRU swap ''' 
        majorLine = self.__SRAM[setID][majorWay]
        toLine = self.__SRAM[setID][way]
        majorLine.swap(toLine)
        for mcList in self.__MCLocList[setID]:
            mcList[majorWay], mcList[way] = mcList[way], mcList[majorWay]
        # update LRU queue
        lruQ = self.__LRUQueue[setID]
        id1 = lruQ.index(way)
        id2 = lruQ.index(majorWay)
        lruQ[id1], lruQ[id2] = lruQ[id2], lruQ[id1]

    def _cache_data(self, setID, tag, data, makeDirty=False):
        cacheSet = self.__SRAM[setID]
        # Merge, comes from write hit or write after read
        if tag in self._tag_list(setID):
            assert(self.__currentMemOp == MemoryOp.WRITE)
            line = cacheSet[self._index_tag(setID, tag)]
            line.data = data
            if makeDirty:
                line.dirty = True
            line.valid = True
        # Comes from read cache or write cache
        else:
            if self._predictPolicy == 'MC': 
                majorWay = tag % self._setAssoc
                line = cacheSet[majorWay]
                # find a place to cache data, no matter it is empty or not
                way = self._replace_decide(setID)
                if cacheSet[way].dirty and cacheSet[way].valid:
                    cacheSet[way].memory_store()
                self._mc_swap(setID, majorWay, way)
                # cache new line
                line.data = data
                line.tag = tag
                line.valid = True
                if makeDirty:
                    line.dirty = True
                # update multi-column index                    
                mcList = self.__MCLocList[setID]
                for i in range(self._setAssoc):
                    if (i == majorWay):
                        mcList[i][majorWay] = True
                    else:
                        mcList[i][majorWay] = False
                self._replace_update(setID, majorWay)

            else:
                way = self._replace_decide(setID)
                self._replace_update(setID, way)
                line = cacheSet[way]
                # conflict, cache flush
                if line.dirty:
                    line.memory_store()
                line.data = data
                line.tag = tag
                line.valid = True
                if makeDirty:
                    line.dirty = True

    def _read_data(self, setID, tag, refresh=True):
        cacheSet = self.__SRAM[setID]
        # MRU way predict policy (support write through policy only)
        if self._predictPolicy == 'MRU':
            way = self.__LRUQueue[setID][-1]
            if tag == cacheSet[way].tag and cacheSet[way].valid:
                self.firstHit += 1
                return ("Hit", cacheSet[way].data)
            if tag in self._tag_list(setID):
                way = self._index_tag(setID, tag)
                if cacheSet[way].valid:
                    self.nonFirstHit += 1
                    if refresh:
                        self._replace_update(setID, way)
                    return ("Hit", cacheSet[way].data)
            return ("Miss", None)
        # Multi-Column way predict policy
        # The difference between PMC and SMC(Sequential Multi-column) is the
        # latency and area of cache in a chip, which has no relation to this 
        # cache behavior simulator. As a matter of fact, PMC and SMC induce the 
        # same miss rate.
        elif self._predictPolicy == 'MC':
            majorWay = tag % self._setAssoc
            logging.debug('majorWay: %d' % majorWay)
            if tag == cacheSet[majorWay].tag and cacheSet[majorWay].valid:
                self.firstHit += 1
                return ("Hit", cacheSet[majorWay].data)
            else:
                selectedLocIndex = self.__MCLocList[setID][majorWay]
                for way in range(self._setAssoc):
                    if not selectedLocIndex[way]: 
                        continue
                    if tag == cacheSet[way].tag and cacheSet[way].valid:
                        self.nonFirstHit += 1
                        self._mc_swap(setID, majorWay, way)
                        if refresh:
                            self._replace_update(setID, majorWay)
                        return ("Hit", cacheSet[majorWay].data)
            return ("Miss", None)

        else: # No predict policy
            # read hit
            if tag in self._tag_list(setID):
                way = self._index_tag(setID, tag)
                if cacheSet[way].valid:
                    if refresh:
                        self._replace_update(setID, way)
                    return ("Hit", cacheSet[way].data)
            # read miss
            return ("Miss", None)

    def query(self, record):
        self.queryCount += 1
        self.__currentAddress = record.address
        self.__currentMemOp = record.memOp
        data = None
        setID = (record.address >> self._offsetWidth) % self._sets
        tag = record.address >> (self._bitWidth - self._tagWidth)
        memOp = record.memOp

#        self.print_LRUQueue(setID)
#        self.print_MCList(setID)
#        self.print_cache(setID)

        if memOp == MemoryOp.READ:
            self.rdQuery += 1
            status, data = self._read_data(setID, tag)
            if status == "Miss":
                self.rdMiss += 1
                logging.info("Read Miss at {:b}".format(self.__currentAddress))
                data = self.__memory_load()
                self._cache_data(setID, tag, data)
            else:
                self.rdHit += 1
                logging.info("Read Hit  at {:b}".format(self.__currentAddress))

        elif memOp == MemoryOp.WRITE:
            self.wtQuery += 1
            if self._writePolicy == "through":
                self.__memory_store()
            elif self._writePolicy == "back":
                status, data = self._read_data(setID, tag, refresh=False)
                if status == "Miss":
                    self.wtMiss += 1
                    logging.info("Write Miss at {:b}".format(self.__currentAddress))
                else:
                    self.wtHit += 1
                    logging.info("Write Hit at {:b}".format(self.__currentAddress))
                self._cache_data(setID, tag, data, makeDirty=True)
            else:
                raise NotImplementedError

        else:
            raise NotImplementedError

    def clear(self):
        for cacheSet in self.__SRAM:
            for line in cacheSet:
                line.clear()
        self.queryCount = 0
        self.rdQuery = 0
        self.wtQuery = 0
        self.rdHit = 0
        self.wtHit = 0
        self.rdMiss = 0
        self.wtMiss = 0
        self.firstHit = 0
        self.nonFirstHit = 0

    def print_LRUQueue(self, setID):
        print(self.__LRUQueue[setID])

    def print_MCList(self, setID):
        print(self.__MCLocList[setID])

    def print_cache(self, setID):
        for line in self.__SRAM[setID]:
            print(line)

    def print_config(self):
        print(
            "size: %dKB, offset: %db, index: %db, tag: %db"
            % (self._size / 1024, self._offsetWidth, self._indexWidth, self._tagWidth)
        )

    def print_record(self):
        if self.rdQuery == 0:
            rdHitRatio = 0
        else:
            rdHitRatio = self.rdHit / self.rdQuery
        if self.wtQuery == 0:
            wtHitRatio = 0
        else:
            wtHitRatio = self.wtHit / self.wtQuery
        print(
            "TotalRead:%d, TotalWrite:%d, ReadHit:%d, WriteHit:%d, Read Hit Rate:%f, Write Hit Rate:%f, First Hit Rate:%f, Non-first Hit Rate:%f, First Hit Rate(aginst hit):%f"
            % (
                self.rdQuery,
                self.wtQuery,
                self.rdHit,
                self.wtHit,
                rdHitRatio,
                wtHitRatio,
                self.firstHit / self.rdQuery,
                self.nonFirstHit / self.rdQuery,
                self.firstHit / self.rdHit
            )
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    c = Cache(size="128kB", setAssoc=1, writePolicy="through", blockSize="8B", predictPolicy=None)
    c.print_config()
    print("*** astar:")
    with open("./traces/astar.trace", "r") as trace:
        for line in trace.readlines():
            line = line.strip().split()
            c.query(MemRecord(line[0], line[1]))
    c.print_record()
    c.clear()
    print("*** bzip2:")
    with open("./traces/bzip2.trace", "r") as trace:
        for line in trace.readlines():
            line = line.strip().split()
            c.query(MemRecord(line[0], line[1]))
    c.print_record()
    c.clear()
    print("*** mcf:")
    with open("./traces/mcf.trace", "r") as trace:
        for line in trace.readlines():
            line = line.strip().split()
            c.query(MemRecord(line[0], line[1]))
    c.print_record()
    c.clear()
    print("*** perlbench:")
    with open("./traces/perlbench.trace", "r") as trace:
        for line in trace.readlines():
            line = line.strip().split()
            c.query(MemRecord(line[0], line[1]))
    c.print_record()