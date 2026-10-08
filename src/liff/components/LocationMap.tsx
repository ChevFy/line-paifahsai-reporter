import { useEffect, useRef, useState } from "react";
import { Loader2, MapPin, Navigation } from "lucide-react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useLanguage } from "../hooks/useLanguage";

type Location = {
  latitude: number;
  longitude: number;
};

type LocationMapProps = {
  value: Location | null;
  onChange: (location: Location) => void;
};

const PAI_CENTER: L.LatLngExpression = [19.358, 98.437];

const locationIcon = L.divIcon({
  className: "location-marker",
  html: '<span class="location-marker-pin"><span>🔥</span></span>',
  iconSize: [42, 42],
  iconAnchor: [21, 38],
});

type LocationErrorKey = "unsupported" | "permissionDenied" | "unavailable";

export default function LocationMap({ value, onChange }: LocationMapProps) {
  const { t } = useLanguage();
  const containerRef = useRef<HTMLDivElement>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const initialValueRef = useRef(value);
  const onChangeRef = useRef(onChange);
  const [isLocating, setIsLocating] = useState(false);
  const [locationError, setLocationError] = useState<LocationErrorKey | null>(null);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    if (!containerRef.current) return;

    const initialValue = initialValueRef.current;
    const map = L.map(containerRef.current).setView(initialValue
      ? [initialValue.latitude, initialValue.longitude]
      : PAI_CENTER, initialValue ? 15 : 11);
    mapRef.current = map;

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);

    const setMarker = (location: Location) => {
      markerRef.current?.remove();
      markerRef.current = L.marker([location.latitude, location.longitude], {
        icon: locationIcon,
      }).addTo(map);
      onChangeRef.current(location);
    };

    if (initialValue) {
      markerRef.current = L.marker([initialValue.latitude, initialValue.longitude], {
        icon: locationIcon,
      }).addTo(map);
    }

    map.on("click", (event) => {
      setMarker({ latitude: event.latlng.lat, longitude: event.latlng.lng });
    });

    return () => {
      markerRef.current = null;
      mapRef.current = null;
      map.remove();
    };
  }, []);

  function selectCurrentLocation() {
    if (!navigator.geolocation) {
      setLocationError("unsupported");
      return;
    }

    setIsLocating(true);
    setLocationError(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const location = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        };
        const map = mapRef.current;
        if (map) {
          markerRef.current?.remove();
          markerRef.current = L.marker([location.latitude, location.longitude], {
            icon: locationIcon,
          }).addTo(map);
          map.setView([location.latitude, location.longitude], 16);
        }
        onChangeRef.current(location);
        setIsLocating(false);
      },
      (error) => {
        setLocationError(
          error.code === error.PERMISSION_DENIED ? "permissionDenied" : "unavailable",
        );
        setIsLocating(false);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    );
  }

  return (
    <>
      <button
        className="current-location-button"
        type="button"
        onClick={selectCurrentLocation}
        disabled={isLocating}
      >
        {isLocating ? <Loader2 className="spin" size={16} /> : <Navigation size={16} />}
        {isLocating ? t.location.locating : t.location.useGps}
      </button>
      <div className="location-map-wrap">
        <div className="location-map" ref={containerRef} aria-label={t.location.mapLabel} />
        {value && (
          <div className="map-coordinates">
            <MapPin size={13} />
            {value.latitude.toFixed(5)}, {value.longitude.toFixed(5)}
          </div>
        )}
      </div>
      {locationError && <p className="error-text" role="alert">{t.location[locationError]}</p>}
    </>
  );
}
