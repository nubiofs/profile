# -*- coding: utf-8 -*-
import os, sys, math ,StringIO, tempfile, time, json, logging
from pywps.Process import WPSProcess
from osgeo import ogr, gdal, osr
from osgeo.gdalconst import *


def densify(geometry,opt,threshold):
      
  gtype = geometry.GetGeometryType()
  if  not (gtype == ogr.wkbLineString or gtype == ogr.wkbMultiLineString):
      raise Exception("The densify function only works on linestring or multilinestring geometries")
      
  g = ogr.Geometry(ogr.wkbLineString)

  # add the first point
  x0 = geometry.GetX(0)
  y0 = geometry.GetY(0)
  g.AddPoint(x0, y0)

  for i in range(1,geometry.GetPointCount()):
      #threshold = 100
      x1 = geometry.GetX(i)
      y1 = geometry.GetY(i)
      if not x0 or not y0:
          raise Exception("First point is null")
      d = distance(x0, x1, y0, y1)

      if opt == "UNIFORM":
          if d != 0.0:
              threshold = float(d)/math.ceil(d/threshold)
          else:
              # duplicate point... throw it out
              continue
      if (d > threshold):
          if opt == "UNIFORM":
              segcount = int(math.ceil(d/threshold))

              dx = (x1 - x0)/segcount
              dy = (y1 - y0)/segcount

              x = x0
              y = y0
              for p in range(1,segcount):
                  x = x + dx
                  y = y + dy
                  g.AddPoint(x, y)
                  
          elif opt == "END":
              segcount = int(math.floor(d/threshold))
              xa = None
              ya = None
              for p in range(1,segcount):
                  if not xa:
                      xn, yn = self.calcpoint(x0,x1,y0,y1,threshold)
                      d = self.distance(x0, xn, y0, yn)
                      xa = xn
                      ya = yn
                      g.AddPoint(xa,ya)
                      continue
                  xn, yn = self.calcpoint(xa, x1, ya, y1, threshold)
                  xa = xn
                  ya = yn
                  g.AddPoint(xa,ya)
                  
          elif opt == "BEGIN":
              
              # I think this might put an extra point in at the end of the 
              # first segment
              segcount = int(math.floor(d/threshold))
              xa = None
              ya = None
              xb = x0
              yb = y0
              remainder = d % threshold
              for p in range(segcount):
                  if not xa:
                      xn, yn = self.calcpoint(x0,x1,y0,y1,remainder)

                      d = self.distance(x0, xn, y0, yn)
                      xa = xn
                      ya = yn
                      g.AddPoint(xa,ya)
                      continue
                  xn, yn = self.calcpoint(xa, x1, ya, y1, threshold)
                  xa = xn
                  ya = yn
                  g.AddPoint(xa,ya)

      g.AddPoint(x1,y1)
      x0 = x1
      y0 = y1

          
  return g

def calcpoint(x0, x1, y0, y1, d):
        a = x1 - x0
        b = y1 - y0
        
        if a == 0:
            xn = x1
            
            if b > 0:
                yn = y0 + d
            else:
                yn = y0 - d
            return (xn, yn)
                      
        theta = degrees(math.atan(abs(b)/abs(a)))
        
        if a > 0 and b > 0:
            omega = theta
        if a < 0 and b > 0:
            omega = 180 - theta
        if a < 0 and b < 0:
            omega = 180 + theta
        if a > 0 and b < 0:
            omega = 360 - theta

        if b == 0:
            yn = y1
            if a > 0:
                xn = x0 + d
            else:
                xn = x0 - d
        else:
            xn = x0 + d*math.cos(radians(omega))
            yn = y0 + d*math.sin(radians(omega))
        
        return (xn, yn)
                    
def distance(x0, x1, y0, y1):
    deltax = x0 - x1
    deltay = y0 - y1
    d2 = (deltax)**2 + (deltay)**2
    d = math.sqrt(d2)
    return d
    
class Process(WPSProcess):
    """Main process class"""
    def __init__(self):
        """Process initialization"""        
        #Read config file if exists and set process variables
        CONFIG = {}
        try:
          with open(os.environ["PYWPS_PROCESSES"] + "/config.json") as json_data:
            CONFIG = json.load(json_data)   
            logging.info("Use config.json")             
        except Exception as error: 
          logging.info("no config.json - Use default configuration instead")  
          logging.info(error)
          
        self.TITLE = CONFIG.get("title", None) or u"Profil en long"
        self.ABSTRACT = CONFIG.get("abstract", None) or u"Generer un profil depuis une ligne passée en paramètre, limite de 1000 points"
        self.GEOMTITLE = CONFIG.get("inputgeomtitle", None) or u"Géometrie au format GML"
        self.OUTPUTTITLE = CONFIG.get("outputtitle", None) or u"Profil calculé"
        self.MAXPOINTSRETURNED = CONFIG.get("maxpointsreturned", None) or 1000
        self.SOURCEPROJECTION = CONFIG.get("sourceprojection", None) or 2154
        self.REFERENTIELS = {"title": "", "values":[],"default":"", "paths": {}}
        referentiels = CONFIG.get("referentiels", None) or {"title": u"Référentiel utilisé en entrée", "values": [{ "name": "srtm", "path": "/var/data/srtm93_03.tif", "default": "true"}]}
        self.REFERENTIELS["title"] = referentiels.get("title", None)
        self.PROJECTIONS = CONFIG.get("projections", None) or {"title": u"Projection - code EPSG utilisé", "values": [2154, 3948, 3857, 4326], "default": 2154}
        self.DISTANCES = CONFIG.get("distances", None) or {"title": u"Distance, pas utilisé","values": [0, 1, 5, 25, 100, 200],"default": 100}
        self.FORMATS = CONFIG.get("formats", None) or {"title": u"Format généré en sortie", "values": ["text", "json"], "default": "text"}   
               
              
        for index, item in enumerate(referentiels["values"]):
          self.REFERENTIELS["paths"][item["name"]] = item["path"]
          self.REFERENTIELS["values"].append(item["name"])
          if item["default"] == "true":
            self.REFERENTIELS["default"] = item["name"]
        logging.info(self.DISTANCES)
        #start_time = time.time()
        WPSProcess.__init__(self,
            identifier = "getProfileProcess",
             title = self.TITLE.encode('utf-8'),
             version = "3.0",
             storeSupported = "true",
             statusSupported = "true",
             abstract = self.ABSTRACT.encode('utf-8'))
        
        self.data = self.addComplexInput(identifier="data",
                    title=self.GEOMTITLE.encode('utf-8'),
                    formats = [{'mimeType':'text/xml'}])

        
       
        self.distance = self.addLiteralInput(identifier="distance",
                    title = self.DISTANCES["title"].encode('utf-8'),
                    type = type(0),
                    default = self.DISTANCES["default"],
                    allowedValues = self.DISTANCES["values"])

        self.outputformat = self.addLiteralInput(identifier="outputformat",
                    title = self.FORMATS["title"].encode('utf-8'),
                    type = type('string'),                    
                    default = self.FORMATS["default"].encode('utf-8'),
                    allowedValues = self.FORMATS["values"])

        self.referentiel = self.addLiteralInput(identifier="referentiel",
                    title = self.REFERENTIELS["title"].encode('utf-8'),
                    type = type('string'),                    
                    default = self.REFERENTIELS["default"],
                    allowedValues = self.REFERENTIELS["values"])

        self.projection = self.addLiteralInput(identifier="projection",
                    title = self.PROJECTIONS["title"].encode('utf-8'),
                    type = type(0),                    
                    default = self.PROJECTIONS["default"],
                    allowedValues = self.PROJECTIONS["values"])
        

        self.result = self.addLiteralOutput(identifier="result",title= self.OUTPUTTITLE.encode('utf-8'),type = type('string'))        
    
    
    def execute(self):      
        
        try:
          inSource = ogr.Open(self.data.getValue())
          inFeature = inSource.GetLayer().GetNextFeature()
          origineline = inFeature.GetGeometryRef()
          transformation = (self.projection.getValue() != self.SOURCEPROJECTION)
        except Exception,e:
          return "Impossible ouvrir fichier: %s" % e

        #Transformation       
        if (transformation):
          insrs = osr.SpatialReference()
          insrs.ImportFromEPSG(self.projection.getValue())
          sourcesrs = osr.SpatialReference()
          sourcesrs.ImportFromEPSG(self.SOURCEPROJECTION)
          trans = osr.CoordinateTransformation(insrs, sourcesrs)
          trans2 = osr.CoordinateTransformation(sourcesrs, insrs)
          origineline.Transform(trans)
          
        start_time = time.time()
        versiongdal=str(gdal.VersionInfo())
        outputFormat = self.outputformat.getValue()
        Referentiel = self.referentiel.getValue()
        Distance = self.distance.getValue()
        gtype = origineline.GetGeometryType()
        self.status.set("Geometry",gtype)
        if  not (gtype == ogr.wkbLineString or gtype == ogr.wkbMultiLineString):
            raise Exception("Le traitement fonctionne uniquement avec des geometries linestring or multilinestring")
        if (Distance > 0):
          self.status.set("Densification de la ligne",20)
          line=densify(origineline,"UNIFORM",Distance)
        else:
          line = origineline
        
        # register all of the GDAL drivers
        gdal.AllRegister()

        # open the image
        self.status.set("Opening MNT",30)
        
        #if Referentiel == 'srtm 90':
        #  img = gdal.Open('/var/data/srtm93_03.tif', GA_ReadOnly) 
        img = gdal.Open(self.REFERENTIELS["paths"][Referentiel], GA_ReadOnly)      
        
        if img is None:
          return Exception('Could not open %s' % (Referentiel))
          sys.exit(1)

        # get image size
        rows = img.RasterYSize
        cols = img.RasterXSize
        bands = img.RasterCount

        # get georeference info
        transform = img.GetGeoTransform()
        xOrigin = transform[0]
        yOrigin = transform[3]
        pixelWidth = transform[1]
        pixelHeight = transform[5]

        if (outputFormat == 'json'):
          reponse = '{"points": ['
        if (outputFormat == 'text'):
          reponse = ""
        self.status.set("Calcul",50)
        distance = 0
        distancetotale = 0
        denivelepos = 0
        deniveleneg = 0
        denivele = 0
        pente = 0
        pentemax = 0
        pentemin = 0
        nodatavalue = None
        band = img.GetRasterBand(1) # 1-based index
        successpoint=0
        dfNoData = band.GetNoDataValue()
        if dfNoData is not None:            
          nodatavalue = dfNoData
        
        allpoints = range(line.GetPointCount())
        processedpoints = allpoints[0:self.MAXPOINTSRETURNED:1]
        for i in processedpoints:
          x = line.GetX(i)
          y = line.GetY(i)
          if (successpoint > 0):            
            precPoint = curPoint
            precAltitude = curAltitude
          curPoint = ogr.CreateGeometryFromWkt('POINT('+str(x) +' ' +str(y)+')')
          # compute pixel offset
          xOffset = int((x - xOrigin) / pixelWidth)
          yOffset = int((y - yOrigin) / pixelHeight)
          
          # read data and add the value to the string
          
          data = band.ReadAsArray(xOffset, yOffset, 1, 1)
          if data is not None:
            if (successpoint == 1):
              firstpoint = precPoint
            
            curAltitude = float(data[0,0])
            #gestion des nodata
            if abs(curAltitude) <1000:
              if (outputFormat == 'json'):
                if (successpoint > 0):
                  distance = precPoint.Distance(curPoint)
                  distancetotale = distancetotale + distance
                  denivele = float(curAltitude - precAltitude)
                  pente = denivele * 100 / distance
                  if (denivele >= 0):
                    denivelepos = denivelepos + denivele
                  else:
                    deniveleneg = deniveleneg + denivele
                  reponse = reponse + ","
                  
                if (transformation):
                  projxy=trans2.TransformPoint(x,y,0.)
                  x=projxy[0]
                  y=projxy[1]
                reponse = reponse + str('[' + str(int(distancetotale)) +
                                      ',' + str(int(x)) +
                                      ',' + str(int(y)) +
                                      ','+ str('%.2f'% curAltitude)+
                                      ',' + str('%.2f'% pente) +']')
                successpoint = successpoint + 1
                lastpoint = curPoint
            else:
              #gestion des nodata (ignore)
              continue
          else:
            return Exception('Le referentiel utilise ne couvre pas integralement la ligne passe en parametre')
          
        if (outputFormat == 'json' and firstpoint is not None):
          executedtime = time.time() - start_time
          if (transformation):
            firstpoint.Transform(trans2)
            lastpoint.Transform(trans2)
          infos = ('"infos": {"denivelepositif":' + str(denivelepos) +
                                  ',"denivelenegatif":' + str(deniveleneg) +
                                  ',"distance":' + str('%.2f'% distancetotale)+
                                  ',"firstpointX":"' + str(firstpoint.GetX()) + '"'+
                                  ',"firstpointY":"' + str(firstpoint.GetY()) + '"'+
                                  ',"lastpointX":"' + str(lastpoint.GetX()) + '"'+
                                  ',"lastpointY":"' + str(lastpoint.GetY()) + '"'+
                                  ',"referentiel":"' + str(Referentiel) + '"'+
                                  ',"processedpoints":"' + str(len(processedpoints)) + '"'+
                                  ',"nodata":"' + str(nodatavalue) + '"'+
                                  ',"executedtime":"' + str(executedtime) + '"'+
                                  ',"gdalversion":"'+ str(versiongdal) +'"}')
          reponse = '{"profile":' + reponse + '],' + infos + '}}'
          self.result.setValue(reponse)
          
        return


