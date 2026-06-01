namespace SmartSubstitution.Api.Settings;

public class PythonAiSettings
{
    public string BaseUrl { get; set; } = "http://localhost:8000";
    public int TimeoutSeconds { get; set; } = 30;
}
