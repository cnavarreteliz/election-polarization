## declare an array variable
years=("2013" "2017" "2021")
country="Chile"
level="region_id"
round="runoff"

## now loop through the above array
for year in "${years[@]}"
do
   python pipeline_files.py -c "$country" -y "$year" -l "$level" -r "$round"  -n 4 -m "nv" -f 1
done