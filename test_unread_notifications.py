"""
Test script for unread notifications system
Run this to verify the system is working correctly
"""
import asyncio
from app.db.leads import (
    get_or_create_lead,
    increment_unread_count,
    mark_conversation_as_read
)
from app.db.queries import get_recent_conversations

async def test_unread_system():
    """Test the unread notifications system"""
    
    print("🧪 Testing Unread Notifications System\n")
    
    # Test phone number
    test_phone = "56999999999"
    
    # Step 1: Create or get lead
    print("1️⃣ Creating/getting test lead...")
    lead = await get_or_create_lead(test_phone, "Test User")
    if lead:
        print(f"   ✅ Lead: {lead['customer_name']} ({lead['phone_number']})")
        print(f"   📊 Initial unread_count: {lead.get('unread_count', 0)}")
    else:
        print("   ❌ Failed to create lead")
        return
    
    # Step 2: Increment unread count
    print("\n2️⃣ Simulating incoming messages...")
    for i in range(3):
        success = await increment_unread_count(test_phone)
        if success:
            print(f"   ✅ Message {i+1} received - counter incremented")
        else:
            print(f"   ❌ Failed to increment counter")
    
    # Step 3: Check updated count
    print("\n3️⃣ Checking updated count...")
    lead = await get_or_create_lead(test_phone, "Test User")
    if lead:
        current_count = lead.get('unread_count', 0)
        print(f"   📊 Current unread_count: {current_count}")
        if current_count == 3:
            print("   ✅ Counter is correct!")
        else:
            print(f"   ⚠️ Expected 3, got {current_count}")
    
    # Step 4: Get recent conversations
    print("\n4️⃣ Checking conversations API...")
    conversations = await get_recent_conversations(limit=10)
    test_conv = next((c for c in conversations if c['phone_number'] == test_phone), None)
    if test_conv:
        print(f"   ✅ Found in conversations:")
        print(f"      - Phone: {test_conv['phone_number']}")
        print(f"      - Name: {test_conv['customer_name']}")
        print(f"      - Unread: {test_conv.get('unread_count', 0)}")
    else:
        print(f"   ⚠️ Test conversation not found in list")
    
    # Step 5: Mark as read
    print("\n5️⃣ Marking conversation as read...")
    success = await mark_conversation_as_read(test_phone)
    if success:
        print("   ✅ Marked as read successfully")
    else:
        print("   ❌ Failed to mark as read")
    
    # Step 6: Verify reset
    print("\n6️⃣ Verifying counter was reset...")
    lead = await get_or_create_lead(test_phone, "Test User")
    if lead:
        final_count = lead.get('unread_count', 0)
        last_read = lead.get('last_read_at')
        print(f"   📊 Final unread_count: {final_count}")
        print(f"   📅 Last read at: {last_read}")
        if final_count == 0:
            print("   ✅ Counter reset successfully!")
        else:
            print(f"   ⚠️ Expected 0, got {final_count}")
    
    print("\n✅ Test completed!")
    print("\n💡 Note: You can delete the test lead from the database if needed:")
    print(f"   DELETE FROM whatsapp_leads WHERE phone_number = '{test_phone}';")

if __name__ == "__main__":
    try:
        asyncio.run(test_unread_system())
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
