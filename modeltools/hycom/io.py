""" MNodule for doing IO on files used by hycom """
import numpy 
import struct
import sys
import logging
import re

# Set up logger
_loglevel=logging.DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(_loglevel)
formatter = logging.Formatter("%(asctime)s - %(name)10s - %(levelname)7s: %(message)s")
ch = logging.StreamHandler()
ch.setLevel(_loglevel)
ch.setFormatter(formatter)
logger.addHandler(ch) 



class AFileError(Exception) :
   pass



class AFile(object) :
   """ Class for doing binary input/output on hycom .a files """
   _huge = 2.0**100
   def __init__(self,idm,jdm,filename,action,mask=False,real4=True,endian="big") :
      self._idm = idm
      self._jdm = jdm 
      self._filename = filename 
      self._action = action 
      self._mask = mask 
      self._real4= real4
      self._endian= endian
      if self._action.lower() not in ["r","w"]  :
         raise AFileError("action argument must be either r(ead) or w(rite)")
      if self._endian.lower() not in ["little","big","native"]  :
         raise AFileError("action argument must be either native, little ort big")

      
      if self._endian.lower() == "native" :
         self._endian=sys.byteorder

      if self._endian.lower() == "big" :
         self._endian_structfmt = ">"
      else :
         self._endian_structfmt = "<"

      logging.debug("Endianness set to %s",self._endian)


      self._zaiost()
      self._zaiopf()



   def _zaiost(self) :
      # Size of output 2D Array
      self._n2drec= ((self._idm*self._jdm+4095)/4096)*4096

      # Init sequenctial record counter
      self._iarec = 0
      self._spval = 2**100.


   def _zaiopf(self) :
      # Open .a and .b file
      self._filea = open(self._filename,self._action+"b")



   def zaiowr_a(self,h,mask,record=None) :
      w=numpy.ones(self._n2drec)*self._spval
      #w[0:self._idm*self._jdm] = h.flatten('F') # Fortran order
      w[0:self._idm*self._jdm] = h.flatten() 

      if record is not None :
         raise AFileError("Seeked writes not yet supported")

      # Calc min and mask
      if self._mask :
         tmp = mask>0
         I=numpy.where(tmp)
         hmax=h(I).max()
         hmin=h(I).min()
         J=numpy.where(~tmp)
         w[J] = self._spval
      else :
         hmax=h.max()
         hmin=h.min()

      if self._real4 :
         struct_fmt="f"
      else :
         struct_fmt="d"
      binpack=struct.pack("%s%d%s"%(self._endian_structfmt,w.size,struct_fmt),*w[:])
      self._filea.write(binpack)
      return hmin,hmax


   def zaiord_a(self,mask,record) :

      # Seek to correct record and read
      self.zaioseek_a(record)
      if self._real4 :
         raw = self._filea.read(self.n2drec*4)
         fmt =  "%s%df"%(self._endian_structfmt,self.n2drec)
      else :
         raw = self._filea.read(self.n2drec*8)
         fmt =  "%s%dd"%(self._endian_structfmt,self.n2drec)
      w =  numpy.array(struct.unpack(fmt,raw))
      w=numpy.ma.masked_where(w>self._huge*.5,w)

      w=w[0:self.idm*self.jdm]
      w.shape=(self.jdm,self.idm)

      return w



   def zaioseek_a(self,record) :
      # Seek to correct record and read
      if self._real4 :
         self._filea.seek(record*self.n2drec*4)
      else :
         self._filea.seek(record*self.n2drec*8)
      return


   def close(self) :
      self._filea.close()


   @property
   def n2drec(self):
      return self._n2drec


   @property
   def idm(self):
      return self._idm


   @property
   def jdm(self):
      return self._jdm


class BFile(object) :

   def __init__(self,filename,action) :
      self._filename=filename
      self._action=action
      self._fileb = open(self._filename,self._action)

   def close(self) :
      self._fileb.close()

   def scanitem(self,item=None,conversion=None) :
      line = self._fileb.readline().strip()
      if item is not None :
         pattern="^(.*)'(%-6s)'[ =]*"%item
         m=re.match(pattern,line)
         print "pattern : ",pattern
         print "line    : ",line
      else :
         m=re.match("^(.*)'(.*)'[ =]*",line)
      print "match:",m
      if m :
         if conversion :
            value = conversion(m.group(1))
         return m.group(2),value
      else :
         return None,None


   def writeitem(self,key,value) :
      print type(value)
      print type(1) 
      if type(value) == type(1) :
         tmp ="%5d   '%-6s'\n"%(value,key)
      else :
         msg = "writeitem not implemented for this type: %s"%type(value)
         raise NotImplementedError,msg

      self._fileb.write(tmp)

   def readline(self) :
      return self._fileb.readline()


   def readrecord(self,record) :
      """ Read single record from archive file"""
      w = self._filea.zaiord_a(1,record)
      return w

   @property
   def fieldnames(self) :
      return set([elem["field"] for elem in self._fields.values()])



class ABFileRegionalGrid(BFile) :
   fieldkeys=["field","min","max"]
   def __init__(self,basename,action,mask=False,real4=True,endian="big",mapflg=-1,idm=None,jdm=None) :

      self._action  = action  
      self._mask    = mask
      self._real4   = real4
      self._endian  = endian
      self._mapflg  = mapflg
      self._idm     = idm
      self._jdm     = jdm

      if action == "w" :
         # TODO: Test that idm, jdm and mapflg is set
         super(ABFileRegionalGrid,self).__init__(basename+".b",action)
         self._filea = AFile(self._idm,self._jdm,basename+".a",action,mask=mask,real4=real4,endian=endian)
         # Regional file .b header
         self.writeitem("idm",self._idm)
         self.writeitem("jdm",self._jdm)
         self.writeitem("mapflg",self._mapflg)
      else :
         super(ABFileRegionalGrid,self).__init__(basename+".b",action)
         self._read_header()
         self._read_field_info()
         self._filea = AFile(self._idm,self._jdm,basename+".a",action,mask=mask,real4=real4,endian=endian)

   def _read_header(self) :
      item,self._idm    = self.scanitem(item="idm",conversion=int)
      item,self._jdm    = self.scanitem(item="jdm",conversion=int)
      item,self._mapflg = self.scanitem(item="mapflg",conversion=int)

   def _read_field_info(self) :
      # Get list of fields from .b file
      #plon:  min,max =      -179.99806       179.99998
      #plat:  min,max =       -15.79576        89.98227
      #...
      self._fields={}
      line=self.readline().strip()
      i=0
      while line :
         fieldname = line[0:4]
         elems = re.split("[ =]+",line)
         elems=[fieldname] + elems[2:]

         self._fields[i] = dict(zip(self.fieldkeys,[el.strip() for el in elems]))
         for k in self.fieldkeys :
            if k in ["min","max","dens","day"] :
               self._fields[i][k] = float(self._fields[i][k])
            elif k in ["k","step"] :
               self._fields[i][k] = int(self._fields[i][k])
         i+=1
         line=self.readline().strip()


   def writefield(self,field,mask,fieldname) :
      hmin,hmax = self._filea.zaiowr_a(field,mask)
      self._fileb.write("%4s:  min,max =%16.5f%16.5f\n"%(fieldname,hmin,hmax))


   def readfield(self,fieldname) :
      """ Read field corresponding to fieldname and level from archive file"""
      record = None
      for i,d in self._fields.items() :
         if d["field"] == fieldname :
            record=i
      if record  is not None :
         w = self.readrecord(record) 
      else :
         w = None
      return w



class ABFileArchv(BFile) :
   fieldkeys=["field","step","day","k","dens","min","max"]
   def __init__(self,basename,action,mask=False,real4=True,endian="big",
         iversn=None,iexpt=None,yrflag=None,idm=None,jdm=None) :

      self._action  = action  
      self._mask    = mask
      self._real4   = real4
      self._endian  = endian
      self._iversn  = iversn
      self._iexpt   = iexpt
      self._yrflag  = yrflag
      self._idm     = idm
      self._jdm     = jdm

      if self._action == "r" :
         super(ABFileArchv,self).__init__(basename+".b","r")
         self._read_header() # Sets internal metadata. Overrides those on input
         self._read_field_info()
      elif self._action == "w" :
         # Need to test if idm, jdm, etc is set at this stage
         raise NotImplementedError,"ABFileArchv writing not implemented"
         super(ABFileArchv,self).__init__(basename+".b",self._action)

      self._filea = AFile(self._idm,self._jdm,basename+".a",self._action,mask=self._mask,real4=self._real4,endian=self._endian)



   def _read_header(self) :
      self._header=[]
      self._header.append(self.readline())
      self._header.append(self.readline())
      self._header.append(self.readline())
      self._header.append(self.readline())

      item,self._iversn = self.scanitem(item="iversn",conversion=int)
      item,self._iexpt  = self.scanitem(item="iexpt",conversion=int)
      item,self._yrflag = self.scanitem(item="yrflag",conversion=int)
      item,self._idm    = self.scanitem(item="idm",conversion=int)
      item,self._jdm    = self.scanitem(item="jdm",conversion=int)

   def _read_field_info(self) :
      # Get list of fields from .b file
      #field       time step  model day  k  dens        min              max
      #montg1   =      67392    351.000  1 25.000   0.0000000E+00   0.0000000E+00
      #
      self._fields={}
      line=self.readline()
      line=self.readline().strip()
      i=0
      while line :
         elems = re.split("[ =]+",line)
         self._fields[i] = dict(zip(self.fieldkeys,[el.strip() for el in elems]))
         for k in self.fieldkeys :
            if k in ["min","max","dens","day"] :
               self._fields[i][k] = float(self._fields[i][k])
            elif k in ["k","step"] :
               self._fields[i][k] = int(self._fields[i][k])
         i+=1
         line=self.readline().strip()


   def readfield(self,fieldname,level) :
      """ Read field corresponding to fieldname and level from archive file"""
      record = None
      for i,d in self._fields.items() :
         if d["field"] == fieldname and level == d["k"] :
            record=i
      if record  is not None :
         w = self.readrecord(record) 
      else :
         w = None
      return w




   @property
   def levels(self) :
      return set([elem["k"] for elem in self._fields.values()])
      
      



         



#      self._fileb.write("%5d    %s\n"%(self._idm,"'idm   '"))
#      self._fileb.write("%5d    %s\n"%(self._idm,"'jdm   '"))
#      self._fileb.write("%5d    %s\n"%(mapflg,"'mapflg'"))
#   22    'iversn' = hycom version number x10
#   10    'iexpt ' = experiment number x10
#    1    'yrflag' = days in year flag
#  800    'idm   ' = longitudinal array size
#  880    'jdm   ' = latitudinal  array size
#
##   def zaiowr(self,field,mask,fieldname) :
##      hmin,hmax = self.zaiowr_a(field,mask)
##      self.zaiowr_b(fieldname,hmin,hmax)
#      
#   open


def write_regional_grid(grid) :
   plon,plat=grid.pgrid()
   ulon,ulat=grid.ugrid()
   vlon,vlat=grid.vgrid()
   qlon,qlat=grid.qgrid()

   regf = ABFileRegionalGrid("regional.grid","w",idm=grid.Nx,jdm=grid.Ny,mapflg=-1)
   regf.writefield(plon,plon,"plon")
   regf.writefield(plat,plat,"plat")
   regf.writefield(qlon,qlon,"qlon")
   regf.writefield(qlat,qlat,"qlat")
   regf.writefield(ulon,ulon,"ulon")
   regf.writefield(ulat,ulat,"ulat")
   regf.writefield(vlon,vlon,"vlon")
   regf.writefield(vlat,vlat,"vlat")

   regf.writefield(grid.p_azimuth(),vlat,"pang")

   regf.writefield(grid.scpx(),plon,"scpx")
   regf.writefield(grid.scpy(),plon,"scpy")
   regf.writefield(grid.scqx(),plon,"scqx")
   regf.writefield(grid.scqy(),plon,"scqy")
   regf.writefield(grid.scux(),plon,"scux")
   regf.writefield(grid.scuy(),plon,"scuy")
   regf.writefield(grid.scvx(),plon,"scvx")
   regf.writefield(grid.scvy(),plon,"scvy")

   regf.writefield(grid.corio(),plon,"cori")
   regf.writefield(grid.aspect_ratio(),plon,"pasp")

   #print regf.n2drec * 19 * 4

   regf.close()



def write_newpos(grid) :
   #logging.debug("Endianness set to %s",endian)
   #logging.debug("Byteswapping is   %s"%str(swap_endian))

   # Number of records
   plon,plat=grid.pgrid()
   nrec = numpy.array([plon.size+plat.size])
   nrec = nrec.astype("i4")

   # Write to file, handle endianness ?
   plon = plon.astype(numpy.float64)
   plat = plat.astype(numpy.float64)
   plon_binpack=struct.pack("=%dd"%plon.size,*plon.flatten()[:])
   plat_binpack=struct.pack("=%dd"%plat.size,*plat.flatten()[:])
   nrec_binpack=struct.pack("=i",plon.size)

   # Fortran sequential unformatted access requires number of elements as first and last 4 bytes...
   fid=open("newpos.uf","wb")
   fid.write(nrec_binpack)
   fid.write(plon_binpack)
   fid.write(plat_binpack)
   fid.write(nrec_binpack)
   fid.close()


   
