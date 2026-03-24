# Source: https://www.mapspam.info/faq/

FAQ
What are the major updates in SPAM 2020 v2.0?
Updated subnational agricultural statistics datasets with newly collected and digitized information
Fixed missing crops in certain districts and countries
Refined the crop extent input layer for countries where cropland area was previously underestimated
Corrected the values of the suitability input layers in some countries
Updated the crop intensity layers
Resolved cases where the sum of the crop physical areas in a pixel exceeded the total pixel area
Corrected pixels reporting implausible yield values
Revised rice and rapeseed distributions in China using additional agricultural information
Fine-trued and updated parameter in the SPAM Model
Updated the administrative boundary in a few countries
What are the major updates in SPAM 2020 v1.0?
The SPAM model has been migrated from a FOXPro program to a R-based program environment, and it is hosted at GitHub as an open access project.
The Global Agro-Ecological Zones have been upgraded to version 4
The baseline map of landcover data has been updated to circa 2020
Subnational data and national statistics have been updated to circa 2020 or the most recent years
Population data has been brought up to date to 2020
Market access data (e.g. road networks) has also been revised to the most recent years.
Two irrigated area layers are used including Global map of irrigated area and Global irrigated area
What are the differences between SPAM 2005 v2.0 and SPAM 2005 v3.2?
ALL regions: An improved cropland surface (From
IIASA/IFPRI
) was used
ALL regions: Input statistics and results are scaled to FAOSTAT (average 2004-2006) released on Jan-8-2016
ALL regions: Except for China, the existing distribution surface was not used
Europe: There is no subsistence share in EU countries for any crop
LAC: Oil palm in Brazil is now assigned to the correct state (previously to Rio Grande do Sul, now Para)
LAC: Ecuador had wrong labeling of level-2 unit, corrected (Zamora was part of Morona Santiago, is now part of Zamora Chinchipe)
ASIA: In India added all GAUL polygons identified as Arunachal Pradesh (country in conflict) to India's state Arunachal Pradesh. This results in more pixels for the old Arunachal Pradesh (and thus India).
ASIA: In India add some of the GAUL polygons identified as Jammu&Kashmir (country in conflict) to India and rename them to state Jammu&Kashmir. Level 2 (district) boundaries taken from GADM. This results in more pixels for India.
SSA: In Ghana, statistics was fixed to include one missing district
In V2.0, the optimization routine allowed "slacks" for cropland, irrigated areas, and sub-national statistics. In some instances, this resulted in allocated areas which exceeded the pixel size. Now only “slacks” for sub-national statistics.
For the following countries, some crops had level-1 entries with -999, which yields no allocation: Czech Republic, Italy, Poland, Sweden, Yemen and New Zealand. This has been fixed.
What are the differences between SPAM 2005 v1.0 and SPAM 2005 v2.0?
Better sub-national statistics for some countries
We revised again the irrigated share of crops to accommodate comments made by the water team at IFPRI.
Better control of model solution when initially it does not solve. One of these controls is to switch off suitability constraints. In the earlier release of SPAM2005 we had to turn off ALL suitability constraints to attempt a solution, now we can do it selectively. This selective turn off of suitability constrains leads to a crop distribution which matches better the agro-ecological conditions, and not just the information on agricultural land and irrigated areas.
Still on the methodology side, when a solution through cross entropy is not found, another attempt is made with a different method (quadratic approximation) to hopefully receive some results, thus avoiding the excessive adjustment of other parameters.
WHAT ARE THE DIFFERENCES BETWEEN SPAM 2000 AND SPAM 2005?
SPAM 2005 evolved over the years. There were a few versions available before this latest one, the best known being SPAM 2000, which can also be downloaded from this website.
Both versions do not differ in the basic underlying methodology, but there are rather big differences in the data.
CROPS
SPAM2000 allocates 20 crops, of which 15 are individual crops and the rest are aggregates of 2 or more crops. In SPAM2005 we expanded the list to 42 crops, which include 32 individual crops, 2 sub-crops and 8 aggregates.
AGRICULTURAL PRODUCTION STATISTICS
In SPAM2000 the sub-national and national crop statistics were centered around the year 2000 and scaled with FAO’s average (1999-2001) figures. Now, in SPAM2005, we centered the sub-national and national crop statistics to the year 2005 and scaled with FAO’s average (2004-2006) figures. Along the same line we assembled, where available irrigation shares and cropping intensities which reflected the condition around the year 2005.
CROPLAND and AREA EQUIPPED FOR IRRIGATION.
The previous version used the M3-Cropland described in the publication Ramankutty et al. (2008), ("Farming the planet: 1. Geographic distribution of global agricultural lands in the year 2000", Global Biogeochemical Cycles, Vol. 22, GB1003, doi:10.1029/2007GB002952. SPAM2005 uses cropland compiled by Fritz et al at (2015)(“Mapping global cropland and field size”, Global Change Biology,doi: 10.1111/gcb.12838). Areas equipped for irrigation were previously take from The Global Map of Irrigation Areas (GMIA) V1 and are now based on V5 (
http://www.fao.org/nr/water/aquastat/irrigationmap/index10.stm
).
CROP SUITABILITIES
The data files generated by GAEZ v 2.0, FAO/IIASA, 2002 (
http://webarchive.iiasa.ac.at/Research/LUC/SAEZ/index.html
) were the basis for our suitability surfaces for SPAM2000. For the current version we relied on the files generated by GAEZ V3.0 2009 (
http://webarchive.iiasa.ac.at/Research/LUC/GAEZv3.0/
). Not only is GAEZ 2009 an updated version of GAEZ 2000, but the list of crops for which there are suitability calculations is more extensive, and thus a better match for SPAM2005.