#!/bin/bash
# Script to run GitHub workflow for each vehicle make

MAKES=(
abarth
acura
aiways
alfaromeo
alpine
audi
bentley
bmw
buick
byd
cadillac
changan
chery
chevrolet
chrysler
citroen
cupra
dacia
dodge
dongfeng
ds
fiat
fisker
ford
genesis
gmc
haval
holden
honda
hyundai
infiniti
jaguar
jeep
kia
ktm
landrover
lexus
lincoln
maruti
maserati
maxus
mazda
mercedes-benz
mg
mini
mitsubishi
nissan
omoda
peugeot
polestar
porsche
ram
renault
rivian
saab
scion
seat
skoda
smart
subaru
suzuki
tata
tesla
toyota
vauxhall-opel
volkswagen
volvo
voyah
)

echo "Starting to run workflow for each vehicle make..."

for REPO_NAME in "${MAKES[@]}"; do
  echo "Running workflow for $REPO_NAME..."
  gh workflow run daily-update.yml -R OBDb/$REPO_NAME
  echo "Workflow triggered for $REPO_NAME"
  # Small delay to avoid hitting rate limits
  sleep 1
done

echo "All workflows have been triggered."